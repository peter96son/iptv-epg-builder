from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .metadata_db import open_metadata_db
from .metadata_enrichment import (
    MOVIE_GROUPS,
    _canonical_metadata_title,
    _detect_metadata_language,
    _is_fiction_candidate,
    _media_type,
    _negative_cache_fresh,
    _programme_language,
    _programme_year,
    _text,
    enrich_metadata,
)
from .utils import normalize_name


STATE_RANK = {
    "partial": 0,
    "unknown": 1,
    "retryable": 2,
    "negative_fresh": 9,
    "complete": 10,
}


def _load_mappings(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_epg(path: Path) -> ET.Element:
    if not path.exists():
        raise FileNotFoundError(f"Missing committed EPG: {path}")
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            return ET.parse(f).getroot()
    return ET.parse(path).getroot()


def _priority(p: ET.Element, groups: dict[str, str]) -> tuple[int, str]:
    cid = (p.get("channel") or "").strip()
    group = groups.get(cid, "")
    title = _text(p, "title").strip().lower()
    if group in MOVIE_GROUPS:
        return (0, cid)
    if title.startswith(("х/ф", "фильм", "кино")):
        return (1, cid)
    if title.startswith(("т/с", "сериал")):
        return (2, cid)
    return (3, cid)


def build_queue(tv: ET.Element, mappings: list[dict]) -> list[dict]:
    """Build a de-duplicated queue and retain how often each work is on air.

    Frequency matters: if the same unresolved film appears 18 times across the
    current EPG, resolving it helps the user more than a one-off obscure title.
    """
    groups = {
        (r.get("output_tvg_id") or "").strip(): (r.get("group") or "").strip()
        for r in mappings
        if (r.get("output_tvg_id") or "").strip()
    }

    unique: dict[tuple[str, str, str, str], dict] = {}
    programmes = list(tv.findall("programme"))
    programmes.sort(key=lambda p: _priority(p, groups))

    now_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")

    for p in programmes:
        cid = (p.get("channel") or "").strip()
        group = groups.get(cid, "")
        title = _text(p, "title").strip()
        if not title or not _is_fiction_candidate(p, group):
            continue

        media_type = _media_type(p, group)
        if not media_type:
            continue

        canonical = _canonical_metadata_title(title, media_type)
        if not canonical:
            continue

        provider_lang = _programme_language(p, title)
        detected = _detect_metadata_language(title, provider_lang)
        language = "ru-RU" if detected == "ru" else "en-US"
        year = _programme_year(p, media_type)
        key = (normalize_name(canonical), year, media_type, language)

        item = unique.get(key)
        if item is None:
            item = {
                "title": canonical,
                "year": year,
                "type": media_type,
                "language": language,
                "channel_id": cid,
                "group": group,
                "priority": _priority(p, groups)[0],
                "occurrences": 0,
                "channels": set(),
                "future_occurrences": 0,
            }
            unique[key] = item

        item["occurrences"] += 1
        item["channels"].add(cid)
        start = (p.get("start") or "").strip()
        if start[:8] >= now_prefix:
            item["future_occurrences"] += 1

        item["priority"] = min(item["priority"], _priority(p, groups)[0])
        if not item["group"] and group:
            item["group"] = group

    out = []
    for item in unique.values():
        item["channel_count"] = len(item.pop("channels"))
        out.append(item)

    return sorted(
        out,
        key=lambda r: (
            r["priority"],
            -r["future_occurrences"],
            -r["occurrences"],
            r["group"],
            r["title"],
            r["year"],
        ),
    )


def _entry_completeness(db, row: dict) -> dict:
    entry = db.resolve_knowledge(
        row["title"], row["year"], row["type"], row["language"]
    )
    if not entry:
        entry = db.get_title(row["title"], row["year"], row["type"], row["language"])

    if not entry:
        return {
            "state": "unknown",
            "overview": False,
            "genres": False,
            "imdb_id": "",
            "miss_count": 0,
            "cached_at": "",
        }

    miss_count = int(entry.get("miss_count") or 0)
    cached_at = str(entry.get("cached_at") or "")

    if entry.get("status") != "found":
        return {
            "state": "negative_fresh" if _negative_cache_fresh(entry) else "retryable",
            "overview": False,
            "genres": False,
            "imdb_id": str(entry.get("imdb_id") or ""),
            "miss_count": miss_count,
            "cached_at": cached_at,
        }

    iid = str(entry.get("imdb_id") or "")
    entity = db.get_imdb_entity(iid) if iid else {}
    overview = bool(str(entry.get("overview") or entity.get("overview") or "").strip())
    genres = bool(entry.get("genre_ids") or entity.get("genres"))
    return {
        "state": "complete" if overview and genres else "partial",
        "overview": overview,
        "genres": genres,
        "imdb_id": iid,
        "miss_count": miss_count,
        "cached_at": cached_at,
    }


def queue_stats(root: Path, queue: list[dict]) -> dict:
    counts = Counter()
    occurrence_counts = Counter()
    with open_metadata_db(root) as db:
        for row in queue:
            status = _entry_completeness(db, row)
            state = status["state"]
            counts[state] += 1
            counts["with_overview"] += int(status["overview"])
            counts["with_genres"] += int(status["genres"])
            counts["with_imdb_id"] += int(bool(status["imdb_id"]))
            occurrence_counts[state] += int(row.get("occurrences") or 1)

    counts["total_unique"] = len(queue)
    counts["remaining"] = (
        counts["unknown"] + counts["retryable"] + counts["partial"]
    )
    counts["remaining_airings"] = (
        occurrence_counts["unknown"]
        + occurrence_counts["retryable"]
        + occurrence_counts["partial"]
    )
    counts["airings_total"] = sum(int(r.get("occurrences") or 1) for r in queue)
    return dict(counts)


def database_stats(root: Path) -> dict:
    """Read normalized DB counters for before/after growth reporting."""
    stats = {}
    with open_metadata_db(root) as db:
        conn = db.conn
        stats["titles"] = int(conn.execute("SELECT COUNT(*) FROM titles").fetchone()[0])
        stats["movies"] = int(conn.execute(
            "SELECT COUNT(*) FROM titles WHERE media_type='movie'"
        ).fetchone()[0])
        stats["series"] = int(conn.execute(
            "SELECT COUNT(*) FROM titles WHERE media_type='series'"
        ).fetchone()[0])
        stats["imdb_entities"] = int(conn.execute(
            "SELECT COUNT(*) FROM imdb_entities"
        ).fetchone()[0])
        stats["aliases"] = int(conn.execute(
            "SELECT COUNT(*) FROM aliases"
        ).fetchone()[0])
        stats["people"] = int(conn.execute(
            "SELECT COUNT(*) FROM people"
        ).fetchone()[0])
        stats["credits"] = int(conn.execute(
            "SELECT COUNT(*) FROM credits"
        ).fetchone()[0])
        stats["complete_metadata"] = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM metadata
            WHERE TRIM(COALESCE(overview_ru,'')) <> ''
              AND genres_json NOT IN ('', '[]')
            """
        ).fetchone()[0])
    return stats


def _adaptive_budget(requested_cap: int, stats: dict) -> int:
    """Spend aggressively while backlog is large, taper off as it shrinks."""
    cap = max(0, int(requested_cap))
    remaining = int(stats.get("remaining") or 0)
    if remaining <= 0 or cap <= 0:
        return 0

    if remaining <= 100:
        target = 250
    elif remaining <= 500:
        target = 500
    elif remaining <= 2_000:
        target = 1_200
    elif remaining <= 5_000:
        target = 2_500
    elif remaining <= 10_000:
        target = 3_500
    else:
        target = 5_000

    return min(cap, target)


def _pending_rows(root: Path, queue: list[dict]) -> list[tuple]:
    """Rank work by user impact, not alphabetically.

    Order:
      1. partial known identities (cheap, high-confidence completion);
      2. never-tried unknown works;
      3. expired negative-cache retries;
    Within each class:
      - movie/scheduled-film groups first;
      - titles appearing in future schedule first;
      - more frequent titles first;
      - fewer prior misses first.
    """
    pending = []
    with open_metadata_db(root) as db:
        for row in queue:
            state = _entry_completeness(db, row)
            if state["state"] in {"complete", "negative_fresh"}:
                continue

            pending.append((
                STATE_RANK.get(state["state"], 5),
                int(row.get("priority") or 0),
                -int(row.get("future_occurrences") or 0),
                -int(row.get("occurrences") or 1),
                int(state.get("miss_count") or 0),
                str(state.get("cached_at") or ""),
                row["title"],
                row["year"],
                row,
                state,
            ))

    pending.sort(key=lambda x: x[:-2])
    return pending


def backfill_tree(source_tv, mappings, root, output, *, budget=5000, dry_run=False):
    queue = build_queue(source_tv, mappings)
    before = queue_stats(root, queue)
    db_before = database_stats(root)
    effective_budget = _adaptive_budget(budget, before)

    report = {
        "mode": "dry-run" if dry_run else "smart-backfill",
        "strategy_version": "13.19",
        "total_unique": before.get("total_unique", 0),
        "before": before,
        "database_before": db_before,
        "requested_budget": max(0, int(budget)),
        "effective_budget": effective_budget,
        "ranking": [
            "partial before unknown before retryable",
            "movie groups first",
            "future airings first",
            "high-frequency titles first",
            "lower miss-count first",
            "fresh negative-cache skipped",
        ],
    }

    if dry_run or effective_budget == 0:
        report.update({
            "remaining": before.get("remaining", 0),
            "with_overview": before.get("with_overview", 0),
            "with_genres": before.get("with_genres", 0),
            "http_spent": 0,
            "database_after": db_before,
            "database_growth": {k: 0 for k in db_before},
        })
    else:
        pending = _pending_rows(root, queue)

        # The HTTP budget remains the true limiter, but also avoid constructing a
        # gigantic synthetic EPG when the queue is huge.
        max_candidates = max(effective_budget * 3, 500)
        pending = pending[:max_candidates]

        tv = ET.Element("tv")
        synthetic_mappings = []
        queue_preview = []

        for i, item in enumerate(pending):
            row, state = item[-2], item[-1]
            cid = f"backfill-{i}"
            p = ET.SubElement(tv, "programme", {"channel": cid})
            ET.SubElement(
                p,
                "title",
                {"lang": "ru" if row["language"] == "ru-RU" else "en"},
            ).text = row["title"]
            if row["year"]:
                ET.SubElement(p, "date").text = row["year"]
            ET.SubElement(p, "category", {"lang": "ru"}).text = (
                "Сериал" if row["type"] == "series" else "Фильм"
            )
            synthetic_mappings.append({
                "output_tvg_id": cid,
                "group": row["group"] or (
                    "Кино" if row["type"] == "movie" else "Сериалы"
                ),
            })
            if len(queue_preview) < 50:
                queue_preview.append({
                    "title": row["title"],
                    "year": row["year"],
                    "type": row["type"],
                    "state": state["state"],
                    "occurrences": row["occurrences"],
                    "future_occurrences": row["future_occurrences"],
                    "channel_count": row["channel_count"],
                    "miss_count": state["miss_count"],
                })

        env_keys = (
            "METADATA_MAX_TITLES",
            "METADATA_MAX_HTTP_REQUESTS",
            "METADATA_MULTI_FALLBACK",
        )
        old = {k: os.environ.get(k) for k in env_keys}
        try:
            os.environ["METADATA_MAX_TITLES"] = str(max(20_000, len(pending) + 100))
            os.environ["METADATA_MAX_HTTP_REQUESTS"] = str(effective_budget)
            os.environ["METADATA_MULTI_FALLBACK"] = "1"
            result = enrich_metadata(tv, synthetic_mappings, root, output)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        after = queue_stats(root, queue)
        db_after = database_stats(root)
        summary = result.get("summary", {})
        growth = {
            key: int(db_after.get(key, 0)) - int(db_before.get(key, 0))
            for key in db_after
        }

        report.update({
            "after": after,
            "database_after": db_after,
            "database_growth": growth,
            "remaining": after.get("remaining", 0),
            "remaining_reduction": (
                int(before.get("remaining") or 0)
                - int(after.get("remaining") or 0)
            ),
            "with_overview": after.get("with_overview", 0),
            "with_genres": after.get("with_genres", 0),
            "http_spent": int(summary.get("metadata_http_requests_used", 0) or 0),
            "http_remaining": int(summary.get("metadata_http_requests_remaining", 0) or 0),
            "stopped_reason": summary.get("metadata_stopped_reason", "completed"),
            "metadata_summary": summary,
            "queue_preview": queue_preview,
        })

    output.mkdir(parents=True, exist_ok=True)
    (output / "metadata-backfill.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Small history file so we can see whether the DB is actually learning.
    history_path = output / "metadata-growth-history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []

    history.append({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": report["mode"],
        "effective_budget": report.get("effective_budget", 0),
        "http_spent": report.get("http_spent", 0),
        "remaining": report.get("remaining", 0),
        "database": report.get("database_after", db_before),
        "growth": report.get("database_growth", {}),
    })
    history = history[-180:]
    history_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smart metadata backfill from committed EPG."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--budget",
        type=int,
        default=int(os.environ.get("BACKFILL_HTTP_BUDGET", "5000")),
        help="Hard cap; smart mode may automatically use less.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = root / "output"
    report = backfill_tree(
        _load_epg(output / "epg.xml.gz"),
        _load_mappings(output / "mapping.csv"),
        root,
        output,
        budget=args.budget,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
