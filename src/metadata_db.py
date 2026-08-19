from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .utils import normalize_name

SCHEMA_VERSION = 5
DEFAULT_DB_NAME = "metadata.sqlite3"
IMDB_ID_RE = re.compile(r"(?i)^tt\d{5,12}$")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_imdb_id(value: str | None) -> str:
    value = (value or "").strip().lower()
    return value if IMDB_ID_RE.fullmatch(value) else ""


def normalize_year(value: str | int | None) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"(?:19|20)\d{2}", text) else ""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


@dataclass(frozen=True)
class TitleKey:
    title: str
    year: str
    media_type: str
    language: str

    @property
    def normalized_title(self) -> str:
        return normalize_name(self.title)


class MetadataDB:
    """Persistent SQLite cache for EPG title identity and metadata.

    The DB replaces the large JSON metadata caches while preserving the same
    conceptual split used by v10:

    * title_cache: schedule title/year/type/lang -> resolved TMDb/IMDb identity
    * imdb_entities: IMDb ID -> rating/votes and entity-level metadata
    * aliases: additional normalized titles -> a resolved IMDb identity

    Schema v2 (v13 stage 1) adds a normalized long-lived knowledge layer:
    * titles: one canonical work identity
    * metadata: one rich metadata row per canonical work
    * people / credits: normalized cast/crew graph
    * aliases.title_id: alias -> canonical work link
    * statistics: persistent counters/state

    The legacy title_cache/imdb_entities tables remain as a compatibility layer
    during the v13 migration. Current enrichment code can keep using the old API
    while every successful write is mirrored into the normalized knowledge layer.
    Existing databases are migrated in place; accumulated metadata is preserved.

    All writes are UPSERTs and therefore idempotent. WAL is enabled so reads
    remain cheap while a build updates the cache.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MetadataDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.conn.execute("BEGIN")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS title_cache (
                normalized_title TEXT NOT NULL,
                display_title TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                media_type TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                imdb_id TEXT NOT NULL DEFAULT '',
                tmdb_id INTEGER,
                tmdb_title TEXT NOT NULL DEFAULT '',
                original_title TEXT NOT NULL DEFAULT '',
                overview TEXT NOT NULL DEFAULT '',
                genre_ids_json TEXT NOT NULL DEFAULT '[]',
                resolved_media_type TEXT NOT NULL DEFAULT '',
                query_title TEXT NOT NULL DEFAULT '',
                attempt TEXT NOT NULL DEFAULT '',
                resolver TEXT NOT NULL DEFAULT '',
                confidence INTEGER,
                similarity REAL,
                attempts INTEGER NOT NULL DEFAULT 0,
                miss_count INTEGER NOT NULL DEFAULT 0,
                cached_at TEXT NOT NULL DEFAULT '',
                rating_checked_at TEXT NOT NULL DEFAULT '',
                extra_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (normalized_title, year, media_type, language)
            );

            CREATE INDEX IF NOT EXISTS idx_title_cache_imdb
                ON title_cache(imdb_id);
            CREATE INDEX IF NOT EXISTS idx_title_cache_status
                ON title_cache(status);
            CREATE INDEX IF NOT EXISTS idx_title_cache_tmdb
                ON title_cache(tmdb_id);

            CREATE TABLE IF NOT EXISTS imdb_entities (
                imdb_id TEXT PRIMARY KEY,
                rating TEXT NOT NULL DEFAULT '',
                votes INTEGER,
                source TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                original_title TEXT NOT NULL DEFAULT '',
                overview TEXT NOT NULL DEFAULT '',
                genres_json TEXT NOT NULL DEFAULT '[]',
                year TEXT NOT NULL DEFAULT '',
                runtime_minutes INTEGER,
                countries_json TEXT NOT NULL DEFAULT '[]',
                poster_url TEXT NOT NULL DEFAULT '',
                kp_rating TEXT NOT NULL DEFAULT '',
                kp_votes INTEGER,
                extra_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS aliases (
                normalized_alias TEXT NOT NULL,
                alias TEXT NOT NULL DEFAULT '',
                imdb_id TEXT NOT NULL,
                year TEXT NOT NULL DEFAULT '',
                media_type TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                confidence INTEGER,
                created_at TEXT NOT NULL DEFAULT '',
                last_seen_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (normalized_alias, year, media_type),
                FOREIGN KEY (imdb_id) REFERENCES imdb_entities(imdb_id)
                    ON UPDATE CASCADE ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_alias_imdb
                ON aliases(imdb_id);

            CREATE TABLE IF NOT EXISTS alias_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_alias TEXT NOT NULL,
                alias TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                media_type TEXT NOT NULL DEFAULT '',
                existing_title_id INTEGER,
                proposed_title_id INTEGER,
                existing_imdb_id TEXT NOT NULL DEFAULT '',
                proposed_imdb_id TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                confidence INTEGER,
                seen_at TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_alias_conflict_key
                ON alias_conflicts(normalized_alias, year, media_type);

            CREATE TABLE IF NOT EXISTS titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imdb_id TEXT UNIQUE,
                tmdb_id INTEGER,
                media_type TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                canonical_title TEXT NOT NULL DEFAULT '',
                original_title TEXT NOT NULL DEFAULT '',
                normalized_canonical_title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                extra_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(tmdb_id, media_type)
            );

            CREATE INDEX IF NOT EXISTS idx_titles_normalized
                ON titles(normalized_canonical_title, year, media_type);
            CREATE INDEX IF NOT EXISTS idx_titles_year_type
                ON titles(year, media_type);

            CREATE TABLE IF NOT EXISTS metadata (
                title_id INTEGER PRIMARY KEY,
                overview_ru TEXT NOT NULL DEFAULT '',
                overview_en TEXT NOT NULL DEFAULT '',
                genres_json TEXT NOT NULL DEFAULT '[]',
                runtime_minutes INTEGER,
                countries_json TEXT NOT NULL DEFAULT '[]',
                languages_json TEXT NOT NULL DEFAULT '[]',
                poster_url TEXT NOT NULL DEFAULT '',
                backdrop_url TEXT NOT NULL DEFAULT '',
                logo_url TEXT NOT NULL DEFAULT '',
                tagline TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '',
                imdb_rating TEXT NOT NULL DEFAULT '',
                imdb_votes INTEGER,
                kp_rating TEXT NOT NULL DEFAULT '',
                kp_votes INTEGER,
                source TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                extra_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (title_id) REFERENCES titles(id)
                    ON UPDATE CASCADE ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id INTEGER UNIQUE,
                imdb_id TEXT UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                normalized_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                extra_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_people_name
                ON people(normalized_name);

            CREATE TABLE IF NOT EXISTS credits (
                title_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                character_name TEXT NOT NULL DEFAULT '',
                department TEXT NOT NULL DEFAULT '',
                job TEXT NOT NULL DEFAULT '',
                billing_order INTEGER,
                source TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (title_id, person_id, role, character_name, job),
                FOREIGN KEY (title_id) REFERENCES titles(id)
                    ON UPDATE CASCADE ON DELETE CASCADE,
                FOREIGN KEY (person_id) REFERENCES people(id)
                    ON UPDATE CASCADE ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_credits_person
                ON credits(person_id);
            CREATE INDEX IF NOT EXISTS idx_credits_title_role
                ON credits(title_id, role);

            CREATE TABLE IF NOT EXISTS statistics (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self._ensure_v2_columns()
        self._migrate_legacy_to_knowledge()
        self.conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # v13 normalized knowledge layer
    # ------------------------------------------------------------------
    def _table_columns(self, table: str) -> set[str]:
        return {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }

    def _ensure_v2_columns(self) -> None:
        """Add non-destructive links to legacy tables on existing databases."""
        title_cols = self._table_columns("title_cache")
        if "knowledge_title_id" not in title_cols:
            self.conn.execute("ALTER TABLE title_cache ADD COLUMN knowledge_title_id INTEGER")

        alias_cols = self._table_columns("aliases")
        if "title_id" not in alias_cols:
            self.conn.execute("ALTER TABLE aliases ADD COLUMN title_id INTEGER")
        if "evidence_count" not in alias_cols:
            self.conn.execute("ALTER TABLE aliases ADD COLUMN evidence_count INTEGER NOT NULL DEFAULT 1")
        if "verified" not in alias_cols:
            self.conn.execute("ALTER TABLE aliases ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
        if "generated_rule" not in alias_cols:
            self.conn.execute("ALTER TABLE aliases ADD COLUMN generated_rule TEXT NOT NULL DEFAULT ''")

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_title_cache_knowledge_title "
            "ON title_cache(knowledge_title_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alias_title_id ON aliases(title_id)"
        )

    @staticmethod
    def _to_int(value: Any) -> int | None:
        text = str(value or "").replace(",", "").replace(" ", "").strip()
        return int(text) if text.isdigit() else None

    def _find_knowledge_title_id(
        self,
        *,
        imdb_id: str = "",
        tmdb_id: int | None = None,
        media_type: str = "",
        canonical_title: str = "",
        year: str = "",
    ) -> int | None:
        iid = normalize_imdb_id(imdb_id)
        if iid:
            row = self.conn.execute(
                "SELECT id FROM titles WHERE imdb_id=?", (iid,)
            ).fetchone()
            if row:
                return int(row["id"])

        if tmdb_id is not None:
            row = self.conn.execute(
                "SELECT id FROM titles WHERE tmdb_id=? AND media_type=?",
                (tmdb_id, media_type or ""),
            ).fetchone()
            if row:
                return int(row["id"])

        normalized = normalize_name(canonical_title)
        if normalized:
            row = self.conn.execute(
                """
                SELECT id FROM titles
                WHERE normalized_canonical_title=? AND year=? AND media_type=?
                ORDER BY id LIMIT 1
                """,
                (normalized, normalize_year(year), media_type or ""),
            ).fetchone()
            if row:
                return int(row["id"])
        return None

    def _upsert_knowledge_title(
        self,
        *,
        imdb_id: str = "",
        tmdb_id: int | None = None,
        media_type: str = "",
        year: str = "",
        canonical_title: str = "",
        original_title: str = "",
        extra: dict | None = None,
    ) -> int | None:
        iid = normalize_imdb_id(imdb_id)
        mt = media_type or ""
        yr = normalize_year(year)
        title = str(canonical_title or original_title or "").strip()
        original = str(original_title or "").strip()
        normalized = normalize_name(title)
        if not (iid or tmdb_id is not None or normalized):
            return None

        existing = self._find_knowledge_title_id(
            imdb_id=iid,
            tmdb_id=tmdb_id,
            media_type=mt,
            canonical_title=title,
            year=yr,
        )
        now = utcnow_iso()
        if existing is None:
            cur = self.conn.execute(
                """
                INSERT INTO titles (
                    imdb_id, tmdb_id, media_type, year, canonical_title,
                    original_title, normalized_canonical_title,
                    created_at, updated_at, extra_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    iid or None, tmdb_id, mt, yr, title, original, normalized,
                    now, now, _json_dumps(extra or {}),
                ),
            )
            return int(cur.lastrowid)

        self.conn.execute(
            """
            UPDATE titles SET
                imdb_id=CASE WHEN ?<>'' THEN ? ELSE imdb_id END,
                tmdb_id=COALESCE(?, tmdb_id),
                media_type=CASE WHEN ?<>'' THEN ? ELSE media_type END,
                year=CASE WHEN ?<>'' THEN ? ELSE year END,
                canonical_title=CASE WHEN ?<>'' THEN ? ELSE canonical_title END,
                original_title=CASE WHEN ?<>'' THEN ? ELSE original_title END,
                normalized_canonical_title=CASE WHEN ?<>'' THEN ? ELSE normalized_canonical_title END,
                updated_at=?,
                extra_json=CASE WHEN ?<>'{}' THEN ? ELSE extra_json END
            WHERE id=?
            """,
            (
                iid, iid, tmdb_id,
                mt, mt, yr, yr,
                title, title, original, original,
                normalized, normalized, now,
                _json_dumps(extra or {}), _json_dumps(extra or {}),
                existing,
            ),
        )
        return existing

    def _upsert_knowledge_metadata(
        self,
        title_id: int | None,
        *,
        language: str = "",
        overview: str = "",
        genres: list | None = None,
        runtime_minutes: Any = None,
        countries: list | None = None,
        languages: list | None = None,
        poster_url: str = "",
        backdrop_url: str = "",
        logo_url: str = "",
        tagline: str = "",
        release_date: str = "",
        imdb_rating: str = "",
        imdb_votes: Any = None,
        kp_rating: str = "",
        kp_votes: Any = None,
        source: str = "",
        checked_at: str = "",
        extra: dict | None = None,
    ) -> None:
        if not title_id:
            return
        lang = (language or "").lower()
        overview_ru = overview if lang.startswith("ru") else ""
        overview_en = overview if lang.startswith("en") else ""
        now = utcnow_iso()
        genres_json = _json_dumps(genres or [])
        countries_json = _json_dumps(countries or [])
        languages_json = _json_dumps(languages or [])
        extra_json = _json_dumps(extra or {})

        self.conn.execute(
            """
            INSERT INTO metadata (
                title_id, overview_ru, overview_en, genres_json, runtime_minutes,
                countries_json, languages_json, poster_url, backdrop_url, logo_url,
                tagline, release_date, imdb_rating, imdb_votes, kp_rating, kp_votes,
                source, checked_at, updated_at, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(title_id) DO UPDATE SET
                overview_ru=CASE WHEN excluded.overview_ru<>'' THEN excluded.overview_ru ELSE metadata.overview_ru END,
                overview_en=CASE WHEN excluded.overview_en<>'' THEN excluded.overview_en ELSE metadata.overview_en END,
                genres_json=CASE WHEN excluded.genres_json<>'[]' THEN excluded.genres_json ELSE metadata.genres_json END,
                runtime_minutes=COALESCE(excluded.runtime_minutes, metadata.runtime_minutes),
                countries_json=CASE WHEN excluded.countries_json<>'[]' THEN excluded.countries_json ELSE metadata.countries_json END,
                languages_json=CASE WHEN excluded.languages_json<>'[]' THEN excluded.languages_json ELSE metadata.languages_json END,
                poster_url=CASE WHEN excluded.poster_url<>'' THEN excluded.poster_url ELSE metadata.poster_url END,
                backdrop_url=CASE WHEN excluded.backdrop_url<>'' THEN excluded.backdrop_url ELSE metadata.backdrop_url END,
                logo_url=CASE WHEN excluded.logo_url<>'' THEN excluded.logo_url ELSE metadata.logo_url END,
                tagline=CASE WHEN excluded.tagline<>'' THEN excluded.tagline ELSE metadata.tagline END,
                release_date=CASE WHEN excluded.release_date<>'' THEN excluded.release_date ELSE metadata.release_date END,
                imdb_rating=CASE WHEN excluded.imdb_rating<>'' THEN excluded.imdb_rating ELSE metadata.imdb_rating END,
                imdb_votes=COALESCE(excluded.imdb_votes, metadata.imdb_votes),
                kp_rating=CASE WHEN excluded.kp_rating<>'' THEN excluded.kp_rating ELSE metadata.kp_rating END,
                kp_votes=COALESCE(excluded.kp_votes, metadata.kp_votes),
                source=CASE WHEN excluded.source<>'' THEN excluded.source ELSE metadata.source END,
                checked_at=CASE WHEN excluded.checked_at<>'' THEN excluded.checked_at ELSE metadata.checked_at END,
                updated_at=excluded.updated_at,
                extra_json=CASE WHEN excluded.extra_json<>'{}' THEN excluded.extra_json ELSE metadata.extra_json END
            """,
            (
                title_id, overview_ru, overview_en, genres_json,
                self._to_int(runtime_minutes), countries_json, languages_json,
                poster_url or "", backdrop_url or "", logo_url or "", tagline or "",
                release_date or "", imdb_rating or "", self._to_int(imdb_votes),
                kp_rating or "", self._to_int(kp_votes), source or "",
                checked_at or "", now, extra_json,
            ),
        )

    def _migrate_legacy_to_knowledge(self) -> None:
        """Idempotently migrate accumulated v11/v12 rows into schema v2."""
        # IMDb entity rows are strongest identities and migrate first.
        for row in self.conn.execute("SELECT * FROM imdb_entities").fetchall():
            title_id = self._upsert_knowledge_title(
                imdb_id=row["imdb_id"],
                media_type="",
                year=row["year"],
                canonical_title=row["title"],
                original_title=row["original_title"],
            )
            self._upsert_knowledge_metadata(
                title_id,
                overview=row["overview"],
                genres=_json_loads(row["genres_json"], []),
                runtime_minutes=row["runtime_minutes"],
                countries=_json_loads(row["countries_json"], []),
                poster_url=row["poster_url"],
                imdb_rating=row["rating"],
                imdb_votes=row["votes"],
                kp_rating=row["kp_rating"],
                kp_votes=row["kp_votes"],
                source=row["source"],
                checked_at=row["checked_at"],
                extra=_json_loads(row["extra_json"], {}),
            )

        # Title cache supplies TMDb IDs, type, language-specific overviews and links.
        rows = self.conn.execute("SELECT * FROM title_cache").fetchall()
        for row in rows:
            if row["status"] != "found":
                continue
            tmdb_id = row["tmdb_id"]
            media_type = row["resolved_media_type"] or row["media_type"]
            title_id = self._upsert_knowledge_title(
                imdb_id=row["imdb_id"],
                tmdb_id=tmdb_id,
                media_type=media_type,
                year=row["year"],
                canonical_title=row["tmdb_title"] or row["display_title"],
                original_title=row["original_title"],
            )
            self._upsert_knowledge_metadata(
                title_id,
                language=row["language"],
                overview=row["overview"],
                genres=_json_loads(row["genre_ids_json"], []),
                source=row["resolver"],
                checked_at=row["cached_at"],
                extra=_json_loads(row["extra_json"], {}),
            )
            if title_id:
                self.conn.execute(
                    """
                    UPDATE title_cache SET knowledge_title_id=?
                    WHERE normalized_title=? AND year=? AND media_type=? AND language=?
                    """,
                    (
                        title_id, row["normalized_title"], row["year"],
                        row["media_type"], row["language"],
                    ),
                )

        # Link accumulated aliases to canonical titles.
        for row in self.conn.execute("SELECT * FROM aliases").fetchall():
            title_id = self._find_knowledge_title_id(
                imdb_id=row["imdb_id"],
                media_type=row["media_type"],
                year=row["year"],
            )
            if title_id:
                self.conn.execute(
                    """
                    UPDATE aliases SET title_id=?
                    WHERE normalized_alias=? AND year=? AND media_type=?
                    """,
                    (title_id, row["normalized_alias"], row["year"], row["media_type"]),
                )

        self.set_stat("knowledge_last_migration_at", utcnow_iso())
        self.set_stat(
            "knowledge_schema_version",
            str(SCHEMA_VERSION),
        )
        self.set_stat("knowledge_resolution_mode", "knowledge-first-smart-aliases")
        self.set_stat("alias_learning_version", "v13-stage3")
        self.set_stat("imdb_local_layer", "official-basics+ratings")

    def _knowledge_row_to_legacy_entry(
        self,
        row: dict,
        *,
        language: str = "",
        query_title: str = "",
        source: str = "knowledge",
        confidence: int | None = None,
    ) -> dict:
        lang = (language or "").lower()
        overview_ru = str(row.get("overview_ru") or "").strip()
        overview_en = str(row.get("overview_en") or "").strip()
        overview = (
            overview_ru if lang.startswith("ru") and overview_ru
            else overview_en if lang.startswith("en") and overview_en
            else overview_ru or overview_en
        )
        genres = row.get("genres") or []
        genre_ids = [int(g) for g in genres if isinstance(g, int) or str(g).isdigit()]
        entity_genres = [str(g) for g in genres if not (isinstance(g, int) or str(g).isdigit())]

        out = {
            "status": "found",
            "imdb_id": str(row.get("imdb_id") or ""),
            "tmdb_id": row.get("tmdb_id"),
            "title": str(row.get("canonical_title") or query_title or ""),
            "original_title": str(row.get("original_title") or ""),
            "overview": overview,
            "genre_ids": genre_ids,
            "entity_genres": entity_genres,
            "resolved_media_type": str(row.get("media_type") or ""),
            "year": str(row.get("year") or ""),
            "query_title": query_title,
            "attempt": source,
            "resolver": source,
            "confidence": confidence if confidence is not None else 100,
            "cached_at": str(row.get("updated_at") or row.get("metadata_checked_at") or ""),
            "imdb_rating": str(row.get("imdb_rating") or ""),
            "imdb_votes": row.get("imdb_votes") or "",
            "rating_source": "knowledge" if row.get("imdb_rating") or row.get("imdb_votes") else "",
            "rating_checked_at": str(row.get("metadata_checked_at") or ""),
            "runtime_minutes": row.get("runtime_minutes"),
            "countries": row.get("countries") or [],
            "languages": row.get("languages") or [],
            "poster_url": str(row.get("poster_url") or ""),
            "backdrop_url": str(row.get("backdrop_url") or ""),
            "logo_url": str(row.get("logo_url") or ""),
            "tagline": str(row.get("tagline") or ""),
            "release_date": str(row.get("release_date") or ""),
            "knowledge_title_id": row.get("id"),
        }
        if not overview or not (genre_ids or entity_genres):
            out["needs_display_refresh"] = True
        return out

    def resolve_knowledge(
        self,
        title: str,
        year: str = "",
        media_type: str = "",
        language: str = "",
    ) -> dict | None:
        """Resolve locally from aliases/titles before any network lookup."""
        normalized = normalize_name(title)
        if not normalized:
            return None
        yr = normalize_year(year)
        mt = media_type or ""

        alias = self.conn.execute(
            """
            SELECT title_id, confidence
            FROM aliases
            WHERE normalized_alias=? AND year=? AND media_type=?
              AND title_id IS NOT NULL
            """,
            (normalized, yr, mt),
        ).fetchone()
        if not alias and yr:
            alias = self.conn.execute(
                """
                SELECT title_id, confidence
                FROM aliases
                WHERE normalized_alias=? AND year='' AND media_type=?
                  AND title_id IS NOT NULL
                """,
                (normalized, mt),
            ).fetchone()
        if alias:
            row = self.get_knowledge_title(int(alias["title_id"]))
            if row:
                return self._knowledge_row_to_legacy_entry(
                    row, language=language, query_title=title,
                    source="knowledge-alias",
                    confidence=alias["confidence"] or 98,
                )

        candidates = []
        for variant, _rule, _penalty in self.alias_variants(title):
            nv = normalize_name(variant)
            if not nv or nv == normalized:
                continue
            rows = self.conn.execute(
                """
                SELECT DISTINCT title_id, confidence FROM aliases
                WHERE normalized_alias=? AND media_type=?
                  AND title_id IS NOT NULL AND (year=? OR year='')
                """,
                (nv, mt, yr),
            ).fetchall()
            candidates.extend(rows)

        ids = {int(r["title_id"]) for r in candidates if r["title_id"] is not None}
        if len(ids) == 1:
            title_id = next(iter(ids))
            row = self.get_knowledge_title(title_id)
            if row:
                conf = max([int(r["confidence"] or 0) for r in candidates if int(r["title_id"]) == title_id] or [96])
                return self._knowledge_row_to_legacy_entry(
                    row, language=language, query_title=title,
                    source="knowledge-smart-alias",
                    confidence=max(94, min(conf, 99)),
                )

        row = self.conn.execute(
            """
            SELECT id FROM titles
            WHERE normalized_canonical_title=? AND year=? AND media_type=?
            ORDER BY id LIMIT 1
            """,
            (normalized, yr, mt),
        ).fetchone()
        if row:
            entity = self.get_knowledge_title(int(row["id"]))
            if entity:
                return self._knowledge_row_to_legacy_entry(
                    entity, language=language, query_title=title,
                    source="knowledge-title", confidence=100,
                )

        if not yr:
            rows = self.conn.execute(
                """
                SELECT id FROM titles
                WHERE normalized_canonical_title=? AND media_type=?
                ORDER BY id LIMIT 2
                """,
                (normalized, mt),
            ).fetchall()
            if len(rows) == 1:
                entity = self.get_knowledge_title(int(rows[0]["id"]))
                if entity:
                    return self._knowledge_row_to_legacy_entry(
                        entity, language=language, query_title=title,
                        source="knowledge-title-unique", confidence=99,
                    )
        return None

    def get_knowledge_title(self, title_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT t.*, m.overview_ru, m.overview_en, m.genres_json,
                   m.runtime_minutes, m.countries_json, m.languages_json,
                   m.poster_url, m.backdrop_url, m.logo_url, m.tagline,
                   m.release_date, m.imdb_rating, m.imdb_votes,
                   m.kp_rating, m.kp_votes, m.source AS metadata_source,
                   m.checked_at AS metadata_checked_at
            FROM titles t
            LEFT JOIN metadata m ON m.title_id=t.id
            WHERE t.id=?
            """,
            (int(title_id),),
        ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["genres"] = _json_loads(out.pop("genres_json", "[]"), [])
        out["countries"] = _json_loads(out.pop("countries_json", "[]"), [])
        out["languages"] = _json_loads(out.pop("languages_json", "[]"), [])
        return out

    def set_stat(self, key: str, value: Any) -> None:
        self.conn.execute(
            """
            INSERT INTO statistics(key, value, updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value, updated_at=excluded.updated_at
            """,
            (str(key), str(value), utcnow_iso()),
        )

    def get_stat(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM statistics WHERE key=?", (str(key),)
        ).fetchone()
        return str(row["value"]) if row else default

    def upsert_person(
        self,
        name: str,
        *,
        tmdb_id: int | None = None,
        imdb_id: str = "",
        extra: dict | None = None,
    ) -> int | None:
        clean_name = str(name or "").strip()
        if not (clean_name or tmdb_id is not None or imdb_id):
            return None
        iid = normalize_imdb_id(imdb_id)
        row = None
        if tmdb_id is not None:
            row = self.conn.execute(
                "SELECT id FROM people WHERE tmdb_id=?", (tmdb_id,)
            ).fetchone()
        if not row and iid:
            row = self.conn.execute(
                "SELECT id FROM people WHERE imdb_id=?", (iid,)
            ).fetchone()
        now = utcnow_iso()
        if row:
            pid = int(row["id"])
            self.conn.execute(
                """
                UPDATE people SET
                    tmdb_id=COALESCE(?, tmdb_id),
                    imdb_id=CASE WHEN ?<>'' THEN ? ELSE imdb_id END,
                    name=CASE WHEN ?<>'' THEN ? ELSE name END,
                    normalized_name=CASE WHEN ?<>'' THEN ? ELSE normalized_name END,
                    updated_at=?,
                    extra_json=CASE WHEN ?<>'{}' THEN ? ELSE extra_json END
                WHERE id=?
                """,
                (
                    tmdb_id, iid, iid, clean_name, clean_name,
                    normalize_name(clean_name), normalize_name(clean_name),
                    now, _json_dumps(extra or {}), _json_dumps(extra or {}), pid,
                ),
            )
            return pid

        cur = self.conn.execute(
            """
            INSERT INTO people(
                tmdb_id, imdb_id, name, normalized_name,
                created_at, updated_at, extra_json
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                tmdb_id, iid or None, clean_name, normalize_name(clean_name),
                now, now, _json_dumps(extra or {}),
            ),
        )
        return int(cur.lastrowid)

    def put_credit(
        self,
        title_id: int,
        person_id: int,
        *,
        role: str,
        character_name: str = "",
        department: str = "",
        job: str = "",
        billing_order: int | None = None,
        source: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO credits(
                title_id, person_id, role, character_name, department,
                job, billing_order, source, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(title_id, person_id, role, character_name, job) DO UPDATE SET
                department=excluded.department,
                billing_order=excluded.billing_order,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (
                int(title_id), int(person_id), role or "", character_name or "",
                department or "", job or "", billing_order, source or "", utcnow_iso(),
            ),
        )

    # ------------------------------------------------------------------
    # Title-resolution cache
    # ------------------------------------------------------------------
    def get_title(self, title: str, year: str = "", media_type: str = "", language: str = "") -> dict | None:
        normalized = normalize_name(title)
        if not normalized:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM title_cache
            WHERE normalized_title=? AND year=? AND media_type=? AND language=?
            """,
            (normalized, normalize_year(year), media_type or "", language or ""),
        ).fetchone()
        return self._title_row_to_dict(row) if row else None

    def put_title(
        self,
        title: str,
        year: str = "",
        media_type: str = "",
        language: str = "",
        entry: dict | None = None,
    ) -> None:
        entry = dict(entry or {})
        normalized = normalize_name(title)
        if not normalized:
            return

        known = {
            "status", "imdb_id", "tmdb_id", "title", "original_title", "overview",
            "genre_ids", "resolved_media_type", "query_title", "attempt", "resolver",
            "confidence", "similarity", "attempts", "miss_count", "cached_at",
            "rating_checked_at", "imdb_rating", "imdb_votes", "rating_source",
        }
        extra = {k: v for k, v in entry.items() if k not in known}
        imdb_id = normalize_imdb_id(entry.get("imdb_id"))
        cached_at = str(entry.get("cached_at") or utcnow_iso())
        tmdb_id = int(entry["tmdb_id"]) if str(entry.get("tmdb_id") or "").isdigit() else None
        resolved_type = str(entry.get("resolved_media_type") or media_type or "")
        knowledge_title_id = None
        if str(entry.get("status") or "") == "found":
            knowledge_title_id = self._upsert_knowledge_title(
                imdb_id=imdb_id,
                tmdb_id=tmdb_id,
                media_type=resolved_type,
                year=year,
                canonical_title=str(entry.get("title") or title),
                original_title=str(entry.get("original_title") or ""),
            )
            self._upsert_knowledge_metadata(
                knowledge_title_id,
                language=language,
                overview=str(entry.get("overview") or ""),
                genres=entry.get("genre_ids") or [],
                imdb_rating=str(entry.get("imdb_rating") or ""),
                imdb_votes=entry.get("imdb_votes"),
                source=str(entry.get("resolver") or entry.get("rating_source") or ""),
                checked_at=str(entry.get("rating_checked_at") or cached_at),
                extra=extra,
            )

        self.conn.execute(
            """
            INSERT INTO title_cache (
                normalized_title, display_title, year, media_type, language,
                status, imdb_id, tmdb_id, tmdb_title, original_title, overview,
                genre_ids_json, resolved_media_type, query_title, attempt, resolver,
                confidence, similarity, attempts, miss_count, cached_at,
                rating_checked_at, extra_json, knowledge_title_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(normalized_title, year, media_type, language) DO UPDATE SET
                display_title=excluded.display_title,
                status=excluded.status,
                imdb_id=excluded.imdb_id,
                tmdb_id=excluded.tmdb_id,
                tmdb_title=excluded.tmdb_title,
                original_title=excluded.original_title,
                overview=excluded.overview,
                genre_ids_json=excluded.genre_ids_json,
                resolved_media_type=excluded.resolved_media_type,
                query_title=excluded.query_title,
                attempt=excluded.attempt,
                resolver=excluded.resolver,
                confidence=excluded.confidence,
                similarity=excluded.similarity,
                attempts=excluded.attempts,
                miss_count=excluded.miss_count,
                cached_at=excluded.cached_at,
                rating_checked_at=excluded.rating_checked_at,
                extra_json=excluded.extra_json,
                knowledge_title_id=COALESCE(excluded.knowledge_title_id, title_cache.knowledge_title_id)
            """,
            (
                normalized, title, normalize_year(year), media_type or "", language or "",
                str(entry.get("status") or ""), imdb_id, tmdb_id,
                str(entry.get("title") or ""), str(entry.get("original_title") or ""),
                str(entry.get("overview") or ""), _json_dumps(entry.get("genre_ids") or []),
                str(entry.get("resolved_media_type") or ""), str(entry.get("query_title") or ""),
                str(entry.get("attempt") or ""), str(entry.get("resolver") or ""),
                int(entry["confidence"]) if str(entry.get("confidence") or "").lstrip("-").isdigit() else None,
                float(entry["similarity"]) if entry.get("similarity") not in (None, "") else None,
                int(entry.get("attempts") or 0), int(entry.get("miss_count") or 0), cached_at,
                str(entry.get("rating_checked_at") or ""), _json_dumps(extra),
                knowledge_title_id,
            ),
        )

        # Preserve v10 entity fields when migrating/feeding old cache entries.
        if imdb_id and any(entry.get(k) not in (None, "") for k in ("imdb_rating", "imdb_votes", "rating_source")):
            self.put_imdb_entity(
                imdb_id,
                {
                    "rating": str(entry.get("imdb_rating") or ""),
                    "votes": entry.get("imdb_votes"),
                    "source": str(entry.get("rating_source") or ""),
                    "checked_at": str(entry.get("rating_checked_at") or cached_at),
                    "title": str(entry.get("title") or ""),
                    "original_title": str(entry.get("original_title") or ""),
                    "overview": str(entry.get("overview") or ""),
                    "year": str(entry.get("year") or year or ""),
                },
            )

    def delete_title(self, title: str, year: str = "", media_type: str = "", language: str = "") -> None:
        self.conn.execute(
            "DELETE FROM title_cache WHERE normalized_title=? AND year=? AND media_type=? AND language=?",
            (normalize_name(title), normalize_year(year), media_type or "", language or ""),
        )

    def _title_row_to_dict(self, row: sqlite3.Row) -> dict:
        out = {
            "status": row["status"],
            "imdb_id": row["imdb_id"],
            "tmdb_id": row["tmdb_id"],
            "title": row["tmdb_title"],
            "original_title": row["original_title"],
            "overview": row["overview"],
            "genre_ids": _json_loads(row["genre_ids_json"], []),
            "resolved_media_type": row["resolved_media_type"],
            "query_title": row["query_title"],
            "attempt": row["attempt"],
            "resolver": row["resolver"],
            "confidence": row["confidence"],
            "similarity": row["similarity"],
            "attempts": row["attempts"],
            "miss_count": row["miss_count"],
            "cached_at": row["cached_at"],
            "rating_checked_at": row["rating_checked_at"],
        }
        out.update(_json_loads(row["extra_json"], {}))
        return out

    # ------------------------------------------------------------------
    # IMDb entity cache
    # ------------------------------------------------------------------
    def get_imdb_entity(self, imdb_id: str) -> dict | None:
        iid = normalize_imdb_id(imdb_id)
        if not iid:
            return None
        row = self.conn.execute("SELECT * FROM imdb_entities WHERE imdb_id=?", (iid,)).fetchone()
        if not row:
            return None
        out = {
            "rating": row["rating"],
            "votes": "" if row["votes"] is None else str(row["votes"]),
            "source": row["source"],
            "checked_at": row["checked_at"],
            "title": row["title"],
            "original_title": row["original_title"],
            "overview": row["overview"],
            "genres": _json_loads(row["genres_json"], []),
            "year": row["year"],
            "runtime_minutes": row["runtime_minutes"],
            "countries": _json_loads(row["countries_json"], []),
            "poster_url": row["poster_url"],
            "kp_rating": row["kp_rating"],
            "kp_votes": "" if row["kp_votes"] is None else str(row["kp_votes"]),
        }
        out.update(_json_loads(row["extra_json"], {}))
        return out

    def put_imdb_entity(self, imdb_id: str, entity: dict | None = None) -> None:
        entity = dict(entity or {})
        iid = normalize_imdb_id(imdb_id)
        if not iid:
            return

        known = {
            "rating", "votes", "source", "checked_at", "title", "original_title",
            "overview", "genres", "year", "runtime_minutes", "countries", "poster_url",
            "kp_rating", "kp_votes",
        }
        extra = {k: v for k, v in entity.items() if k not in known}

        def to_int(value: Any) -> int | None:
            text = str(value or "").replace(",", "").replace(" ", "").strip()
            return int(text) if text.isdigit() else None

        self.conn.execute(
            """
            INSERT INTO imdb_entities (
                imdb_id, rating, votes, source, checked_at, title, original_title,
                overview, genres_json, year, runtime_minutes, countries_json,
                poster_url, kp_rating, kp_votes, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(imdb_id) DO UPDATE SET
                rating=excluded.rating,
                votes=excluded.votes,
                source=excluded.source,
                checked_at=excluded.checked_at,
                title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE imdb_entities.title END,
                original_title=CASE WHEN excluded.original_title<>'' THEN excluded.original_title ELSE imdb_entities.original_title END,
                overview=CASE WHEN excluded.overview<>'' THEN excluded.overview ELSE imdb_entities.overview END,
                genres_json=CASE WHEN excluded.genres_json<>'[]' THEN excluded.genres_json ELSE imdb_entities.genres_json END,
                year=CASE WHEN excluded.year<>'' THEN excluded.year ELSE imdb_entities.year END,
                runtime_minutes=COALESCE(excluded.runtime_minutes, imdb_entities.runtime_minutes),
                countries_json=CASE WHEN excluded.countries_json<>'[]' THEN excluded.countries_json ELSE imdb_entities.countries_json END,
                poster_url=CASE WHEN excluded.poster_url<>'' THEN excluded.poster_url ELSE imdb_entities.poster_url END,
                kp_rating=CASE WHEN excluded.kp_rating<>'' THEN excluded.kp_rating ELSE imdb_entities.kp_rating END,
                kp_votes=COALESCE(excluded.kp_votes, imdb_entities.kp_votes),
                extra_json=excluded.extra_json
            """,
            (
                iid, str(entity.get("rating") or ""), to_int(entity.get("votes")),
                str(entity.get("source") or ""), str(entity.get("checked_at") or utcnow_iso()),
                str(entity.get("title") or ""), str(entity.get("original_title") or ""),
                str(entity.get("overview") or ""), _json_dumps(entity.get("genres") or []),
                normalize_year(entity.get("year")), to_int(entity.get("runtime_minutes")),
                _json_dumps(entity.get("countries") or []), str(entity.get("poster_url") or ""),
                str(entity.get("kp_rating") or ""), to_int(entity.get("kp_votes")), _json_dumps(extra),
            ),
        )

        title_id = self._upsert_knowledge_title(
            imdb_id=iid,
            media_type=str(entity.get("media_type") or ""),
            year=entity.get("year"),
            canonical_title=str(entity.get("title") or ""),
            original_title=str(entity.get("original_title") or ""),
            tmdb_id=self._to_int(entity.get("tmdb_id")),
        )
        self._upsert_knowledge_metadata(
            title_id,
            language=str(entity.get("language") or ""),
            overview=str(entity.get("overview") or ""),
            genres=entity.get("genres") or [],
            runtime_minutes=entity.get("runtime_minutes"),
            countries=entity.get("countries") or [],
            languages=entity.get("languages") or [],
            poster_url=str(entity.get("poster_url") or ""),
            backdrop_url=str(entity.get("backdrop_url") or ""),
            logo_url=str(entity.get("logo_url") or ""),
            tagline=str(entity.get("tagline") or ""),
            release_date=str(entity.get("release_date") or ""),
            imdb_rating=str(entity.get("rating") or ""),
            imdb_votes=entity.get("votes"),
            kp_rating=str(entity.get("kp_rating") or ""),
            kp_votes=entity.get("kp_votes"),
            source=str(entity.get("source") or ""),
            checked_at=str(entity.get("checked_at") or ""),
            extra=extra,
        )

    # ------------------------------------------------------------------
    # Aliases / learning
    # ------------------------------------------------------------------
    def get_alias(self, alias: str, year: str = "", media_type: str = "") -> dict | None:
        normalized = normalize_name(alias)
        if not normalized:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM aliases
            WHERE normalized_alias=? AND year=? AND media_type=?
            """,
            (normalized, normalize_year(year), media_type or ""),
        ).fetchone()
        if not row and year:
            row = self.conn.execute(
                """
                SELECT * FROM aliases
                WHERE normalized_alias=? AND year='' AND media_type=?
                """,
                (normalized, media_type or ""),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def alias_variants(value: str) -> list[tuple[str, str, int]]:
        raw = re.sub(r"\s+", " ", str(value or "")).strip()
        if not raw:
            return []

        out: list[tuple[str, str, int]] = []
        seen: set[str] = set()

        def add(text: str, rule: str, penalty: int = 0):
            text = re.sub(r"\s+", " ", text or "").strip(" -–—:;,.")
            n = normalize_name(text)
            # Do not deduplicate variants through normalize_name here: that
            # normalizer intentionally collapses some provider-quality noise,
            # which would hide useful learned aliases such as "Title 4K" -> "Title".
            seen_key = re.sub(r"\s+", " ", text).casefold()
            if len(n) < 3 or seen_key in seen:
                return
            seen.add(seen_key)
            out.append((text, rule, penalty))

        add(raw, "exact", 0)
        add(raw.replace("ё", "е").replace("Ё", "Е"), "yo-e", 0)
        add(re.sub(r'[«»„“”"]', "", raw), "quotes", 1)

        no_prefix = re.sub(
            r"(?i)^\s*(?:х/ф|м/ф|т/с|д/с|д/ф|сериал|фильм|кино)\s*[:.\-–—]?\s*",
            "",
            raw,
        )
        add(no_prefix, "provider-prefix", 0)

        no_quality = re.sub(
            r"(?i)\s*(?:[\[(]\s*)?(?:UHD|FHD|HD|4K|2160P|1080P)(?:\s*[\])])?\s*$",
            "",
            no_prefix,
        )
        add(no_quality, "quality-suffix", 1)

        no_year = re.sub(
            r"(?i)\s*[\[(]?\s*(?:19\d{2}|20\d{2})\s*(?:год)?\s*[\])]?\s*$",
            "",
            no_quality,
        )
        add(no_year, "year-suffix", 1)

        punct = re.sub(r"\s*[-–—]\s*", " ", no_year)
        add(punct, "dash-spacing", 2)

        return out

    def _record_alias_conflict(
        self, *, alias: str, year: str, media_type: str, existing: Any,
        proposed_title_id: int | None, proposed_imdb_id: str, source: str,
        confidence: int | None, detail: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO alias_conflicts(
                normalized_alias, alias, year, media_type,
                existing_title_id, proposed_title_id,
                existing_imdb_id, proposed_imdb_id,
                source, confidence, seen_at, detail
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                normalize_name(alias), alias, normalize_year(year), media_type or "",
                existing["title_id"] if existing else None, proposed_title_id,
                str(existing["imdb_id"] or "") if existing else "",
                proposed_imdb_id or "", source or "", confidence,
                utcnow_iso(), detail or "",
            ),
        )

    def learn_alias(
        self,
        alias: str,
        imdb_id: str,
        year: str = "",
        media_type: str = "",
        *,
        source: str = "learned",
        confidence: int | None = None,
        generated_rule: str = "",
        verified: bool = False,
    ) -> bool:
        normalized = normalize_name(alias)
        iid = normalize_imdb_id(imdb_id)
        if not normalized or not iid:
            return False

        self.conn.execute(
            "INSERT INTO imdb_entities(imdb_id, checked_at) VALUES(?, '') "
            "ON CONFLICT(imdb_id) DO NOTHING",
            (iid,),
        )
        title_id = self._find_knowledge_title_id(
            imdb_id=iid, year=year, media_type=media_type
        )
        if title_id is None:
            title_id = self._upsert_knowledge_title(
                imdb_id=iid, year=year, media_type=media_type,
                canonical_title=alias,
            )

        yr = normalize_year(year)
        mt = media_type or ""
        existing = self.conn.execute(
            "SELECT * FROM aliases WHERE normalized_alias=? AND year=? AND media_type=?",
            (normalized, yr, mt),
        ).fetchone()

        if existing:
            same = (
                (existing["title_id"] is not None and title_id is not None and int(existing["title_id"]) == int(title_id))
                or normalize_imdb_id(existing["imdb_id"]) == iid
            )
            if not same:
                self._record_alias_conflict(
                    alias=alias, year=yr, media_type=mt, existing=existing,
                    proposed_title_id=title_id, proposed_imdb_id=iid,
                    source=source, confidence=confidence,
                    detail="conflicting-canonical-identity",
                )
                return False
            self.conn.execute(
                """
                UPDATE aliases SET
                    alias=?, imdb_id=?, title_id=COALESCE(?, title_id),
                    source=CASE WHEN ?<>'' THEN ? ELSE source END,
                    confidence=MAX(COALESCE(confidence,0), COALESCE(?,0)),
                    evidence_count=COALESCE(evidence_count,1)+1,
                    verified=MAX(COALESCE(verified,0), ?),
                    generated_rule=CASE WHEN ?<>'' THEN ? ELSE generated_rule END,
                    last_seen_at=?
                WHERE normalized_alias=? AND year=? AND media_type=?
                """,
                (
                    alias, iid, title_id, source or "", source or "", confidence,
                    1 if verified else 0, generated_rule or "", generated_rule or "",
                    utcnow_iso(), normalized, yr, mt,
                ),
            )
            return True

        now = utcnow_iso()
        self.conn.execute(
            """
            INSERT INTO aliases(
                normalized_alias, alias, imdb_id, year, media_type, source,
                confidence, created_at, last_seen_at, title_id,
                evidence_count, verified, generated_rule
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                normalized, alias, iid, yr, mt, source or "", confidence,
                now, now, title_id, 1, 1 if verified else 0, generated_rule or "",
            ),
        )
        return True

    def teach_alias_family(
        self,
        values: list[str],
        imdb_id: str,
        year: str = "",
        media_type: str = "",
        *,
        source: str = "auto-family",
        confidence: int = 98,
    ) -> int:
        learned = 0
        for value in values:
            for variant, rule, penalty in self.alias_variants(value):
                conf = max(90, int(confidence) - int(penalty))
                if self.learn_alias(
                    variant, imdb_id, year, media_type,
                    source=source, confidence=conf,
                    generated_rule=rule, verified=confidence >= 97,
                ):
                    learned += 1
        return learned

    def put_alias(
        self,
        alias: str,
        imdb_id: str,
        year: str = "",
        media_type: str = "",
        source: str = "learned",
        confidence: int | None = None,
    ) -> None:
        self.learn_alias(
            alias, imdb_id, year, media_type,
            source=source, confidence=confidence,
            verified=bool((confidence or 0) >= 97),
        )

    # ------------------------------------------------------------------
    # Migration from v10 JSON caches
    # ------------------------------------------------------------------
    def migrate_v10_json(self, metadata_cache: Path | str | None, imdb_cache: Path | str | None) -> dict[str, int]:
        stats = {"title_rows": 0, "entity_rows": 0, "skipped": 0}

        if metadata_cache:
            path = Path(metadata_cache)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw = {}
                entries = raw.get("entries", raw) if isinstance(raw, dict) else {}
                if isinstance(entries, dict):
                    for key, entry in entries.items():
                        if not isinstance(entry, dict):
                            stats["skipped"] += 1
                            continue
                        parts = str(key).split("|")
                        if len(parts) < 4:
                            stats["skipped"] += 1
                            continue
                        normalized_title, year, media_type, language = parts[0], parts[1], parts[2], "|".join(parts[3:])
                        display = str(entry.get("query_title") or entry.get("title") or normalized_title)
                        # Use the normalized key from JSON verbatim by supplying a title that normalizes equivalently.
                        # If normalization evolved, preserving the display value is still safe; lookups will simply miss
                        # the old row and repopulate it.
                        self.put_title(display, year, media_type, language, entry)
                        stats["title_rows"] += 1

        if imdb_cache:
            path = Path(imdb_cache)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw = {}
                entities = raw.get("entries", raw) if isinstance(raw, dict) else {}
                if isinstance(entities, dict):
                    for imdb_id, entity in entities.items():
                        if not isinstance(entity, dict) or not normalize_imdb_id(imdb_id):
                            stats["skipped"] += 1
                            continue
                        self.put_imdb_entity(imdb_id, entity)
                        stats["entity_rows"] += 1

        self.conn.commit()
        return stats

    def counts(self) -> dict[str, int]:
        return {
            "titles": int(self.conn.execute("SELECT COUNT(*) FROM title_cache").fetchone()[0]),
            "imdb_entities": int(self.conn.execute("SELECT COUNT(*) FROM imdb_entities").fetchone()[0]),
            "aliases": int(self.conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]),
            "knowledge_titles": int(self.conn.execute("SELECT COUNT(*) FROM titles").fetchone()[0]),
            "knowledge_metadata": int(self.conn.execute("SELECT COUNT(*) FROM metadata").fetchone()[0]),
            "people": int(self.conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]),
            "credits": int(self.conn.execute("SELECT COUNT(*) FROM credits").fetchone()[0]),
            "alias_conflicts": int(self.conn.execute("SELECT COUNT(*) FROM alias_conflicts").fetchone()[0]),
        }

    def checkpoint(self) -> None:
        self.conn.commit()
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass


def open_metadata_db(root: Path) -> MetadataDB:
    return MetadataDB(root / ".cache" / "metadata" / DEFAULT_DB_NAME)
