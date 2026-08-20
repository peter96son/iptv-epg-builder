from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from .metadata_db import MetadataDB
from .utils import normalize_name

TMDB_URL = "https://api.themoviedb.org/3"
STAGE7_VERSION = "13.10-stage7"
DEFAULT_CAST_LIMIT = 8


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_json(url: str, timeout: int = 12) -> dict:
    # Import lazily to reuse the project's retry/HTTP behavior without a cycle at import time.
    from .metadata_enrichment import _http_json as project_http_json
    return project_http_json(url, timeout)


def _tmdb_credits(api_key: str, tmdb_id: int, media_type: str, timeout: int = 12) -> dict:
    endpoint = "movie" if media_type == "movie" else "tv"
    params = urllib.parse.urlencode({"api_key": api_key})
    return _http_json(f"{TMDB_URL}/{endpoint}/{int(tmdb_id)}/credits?{params}", timeout)


def _knowledge_title_id(db: MetadataDB, entry: dict) -> int | None:
    title_id = entry.get("knowledge_title_id")
    if title_id:
        return int(title_id)
    return db._find_knowledge_title_id(
        imdb_id=str(entry.get("imdb_id") or ""),
        tmdb_id=int(entry["tmdb_id"]) if entry.get("tmdb_id") is not None else None,
        media_type=str(entry.get("resolved_media_type") or ""),
        canonical_title=str(entry.get("title") or ""),
        year=str(entry.get("year") or ""),
    )


def _upsert_person(db: MetadataDB, person: dict) -> int | None:
    tmdb_id = person.get("id")
    name = str(person.get("name") or "").strip()
    if not name:
        return None
    now = _now()
    row = None
    if tmdb_id is not None:
        row = db.conn.execute("SELECT id FROM people WHERE tmdb_id=?", (int(tmdb_id),)).fetchone()
    if row is None:
        row = db.conn.execute(
            "SELECT id FROM people WHERE normalized_name=? ORDER BY id LIMIT 1",
            (normalize_name(name),),
        ).fetchone()
    extra = {
        "original_name": str(person.get("original_name") or ""),
        "profile_path": str(person.get("profile_path") or ""),
        "known_for_department": str(person.get("known_for_department") or ""),
    }
    import json
    extra_json = json.dumps(extra, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if row:
        pid = int(row["id"])
        db.conn.execute(
            """UPDATE people SET
               tmdb_id=COALESCE(tmdb_id, ?),
               name=CASE WHEN ?<>'' THEN ? ELSE name END,
               normalized_name=CASE WHEN ?<>'' THEN ? ELSE normalized_name END,
               updated_at=?,
               extra_json=CASE WHEN ?<>'{}' THEN ? ELSE extra_json END
               WHERE id=?""",
            (int(tmdb_id) if tmdb_id is not None else None,
             name, name, normalize_name(name), normalize_name(name),
             now, extra_json, extra_json, pid),
        )
        return pid
    cur = db.conn.execute(
        """INSERT INTO people
           (tmdb_id, imdb_id, name, normalized_name, created_at, updated_at, extra_json)
           VALUES (?, NULL, ?, ?, ?, ?, ?)""",
        (int(tmdb_id) if tmdb_id is not None else None,
         name, normalize_name(name), now, now, extra_json),
    )
    return int(cur.lastrowid)


def _store_credit(
    db: MetadataDB,
    title_id: int,
    person_id: int,
    *,
    role: str,
    character_name: str = "",
    department: str = "",
    job: str = "",
    billing_order: int | None = None,
) -> None:
    db.conn.execute(
        """INSERT INTO credits
           (title_id, person_id, role, character_name, department, job,
            billing_order, source, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(title_id, person_id, role, character_name, job) DO UPDATE SET
             department=excluded.department,
             billing_order=COALESCE(excluded.billing_order, credits.billing_order),
             source=excluded.source,
             updated_at=excluded.updated_at""",
        (title_id, person_id, role, character_name, department, job,
         billing_order, "tmdb", _now()),
    )


def store_tmdb_credits(db: MetadataDB, entry: dict, payload: dict, cast_limit: int = DEFAULT_CAST_LIMIT) -> dict:
    """Persist directors + top billed cast into Stage-1 people/credits tables."""
    title_id = _knowledge_title_id(db, entry)
    if not title_id:
        return {"stored": 0, "directors": 0, "actors": 0, "reason": "no_title_id"}

    directors = 0
    actors = 0

    for crew in payload.get("crew") or []:
        if str(crew.get("job") or "").strip().lower() != "director":
            continue
        pid = _upsert_person(db, crew)
        if not pid:
            continue
        _store_credit(
            db, title_id, pid, role="director",
            department=str(crew.get("department") or ""),
            job=str(crew.get("job") or "Director"),
        )
        directors += 1

    cast = sorted(
        [x for x in (payload.get("cast") or []) if str(x.get("name") or "").strip()],
        key=lambda x: int(x.get("order") if x.get("order") is not None else 999999),
    )[:max(0, int(cast_limit))]
    for actor in cast:
        pid = _upsert_person(db, actor)
        if not pid:
            continue
        _store_credit(
            db, title_id, pid, role="actor",
            character_name=str(actor.get("character") or ""),
            department=str(actor.get("known_for_department") or "Acting"),
            billing_order=int(actor.get("order")) if actor.get("order") is not None else None,
        )
        actors += 1

    db.conn.commit()
    return {"stored": directors + actors, "directors": directors, "actors": actors}


def get_stored_credits(db: MetadataDB, entry: dict, cast_limit: int = DEFAULT_CAST_LIMIT) -> dict:
    title_id = _knowledge_title_id(db, entry)
    if not title_id:
        return {"directors": [], "actors": []}

    directors = [
        str(r["name"])
        for r in db.conn.execute(
            """SELECT p.name FROM credits c JOIN people p ON p.id=c.person_id
               WHERE c.title_id=? AND c.role='director'
               ORDER BY COALESCE(c.billing_order, 999999), p.name""",
            (title_id,),
        ).fetchall()
        if str(r["name"]).strip()
    ]
    actors = [
        {"name": str(r["name"]), "character": str(r["character_name"] or "")}
        for r in db.conn.execute(
            """SELECT p.name, c.character_name FROM credits c JOIN people p ON p.id=c.person_id
               WHERE c.title_id=? AND c.role='actor'
               ORDER BY COALESCE(c.billing_order, 999999), p.name LIMIT ?""",
            (title_id, max(0, int(cast_limit))),
        ).fetchall()
        if str(r["name"]).strip()
    ]
    return {"directors": directors, "actors": actors}


def ensure_credits(
    db: MetadataDB,
    entry: dict,
    api_key: str,
    *,
    timeout: int = 12,
    cast_limit: int = DEFAULT_CAST_LIMIT,
    allow_http: bool = True,
) -> tuple[dict, int]:
    """Return credits and number of HTTP calls spent (0 or 1). Cache/database first."""
    existing = get_stored_credits(db, entry, cast_limit)
    if existing["directors"] or existing["actors"]:
        return existing, 0
    if not allow_http or not api_key or not entry.get("tmdb_id"):
        return existing, 0

    media_type = str(entry.get("resolved_media_type") or "")
    if media_type not in {"movie", "series"}:
        return existing, 0
    payload = _tmdb_credits(api_key, int(entry["tmdb_id"]), media_type, timeout)
    store_tmdb_credits(db, entry, payload, cast_limit)
    return get_stored_credits(db, entry, cast_limit), 1


def apply_xmltv_credits(programme: ET.Element, credits: dict) -> bool:
    """Render standard XMLTV <credits> without polluting UHF's short description."""
    directors = [str(x).strip() for x in credits.get("directors") or [] if str(x).strip()]
    actors = credits.get("actors") or []
    if not directors and not actors:
        return False

    old = programme.find("credits")
    if old is not None:
        programme.remove(old)
    node = ET.Element("credits")

    for name in directors:
        ET.SubElement(node, "director").text = name
    for actor in actors:
        if isinstance(actor, dict):
            name = str(actor.get("name") or "").strip()
            character = str(actor.get("character") or "").strip()
        else:
            name, character = str(actor).strip(), ""
        if not name:
            continue
        elem = ET.SubElement(node, "actor")
        if character:
            elem.set("role", character)
        elem.text = name

    # XMLTV convention places credits before date/category/desc; exact sibling order is
    # not semantically important, but inserting before date keeps output tidy.
    children = list(programme)
    insert_at = next(
        (i for i, child in enumerate(children) if child.tag in {"date", "category", "desc", "icon", "url"}),
        len(children),
    )
    programme.insert(insert_at, node)
    return True
