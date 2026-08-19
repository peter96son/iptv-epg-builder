from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from .metadata_db import open_metadata_db
from .metadata_enrichment import (
    MOVIE_GROUPS,
    _canonical_metadata_title,
    _categories,
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
    groups = {
        (r.get("output_tvg_id") or "").strip(): (r.get("group") or "").strip()
        for r in mappings
        if (r.get("output_tvg_id") or "").strip()
    }

    unique: dict[tuple[str, str, str, str], dict] = {}
    programmes = list(tv.findall("programme"))
    programmes.sort(key=lambda p: _priority(p, groups))

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
        unique.setdefault(key, {
            "title": canonical,
            "year": year,
            "type": media_type,
            "language": language,
            "channel_id": cid,
            "group": group,
            "priority": _priority(p, groups)[0],
        })

    return sorted(
        unique.values(),
        key=lambda r: (r["priority"], r["group"], r["title"], r["year"]),
    )


def _entry_completeness(db, row: dict) -> dict:
    entry = db.get_title(row["title"], row["year"], row["type"], row["language"])
    if not entry:
        return {"state": "unknown", "overview": False, "genres": False, "imdb_id": ""}

    if entry.get("status") != "found":
        return {
            "state": "negative_fresh" if _negative_cache_fresh(entry) else "retryable",
            "overview": False,
            "genres": False,
            "imdb_id": str(entry.get("imdb_id") or ""),
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
    }


def queue_stats(root: Path, queue: list[dict]) -> dict:
    counts = Counter()
    with open_metadata_db(root) as db:
        for row in queue:
            status = _entry_completeness(db, row)
            counts[status["state"]] += 1
            counts["with_overview"] += int(status["overview"])
            counts["with_genres"] += int(status["genres"])
            counts["with_imdb_id"] += int(bool(status["imdb_id"]))
    counts["total_unique"] = len(queue)
    counts["remaining"] = (
        counts["unknown"] + counts["retryable"] + counts["partial"]
    )
    return dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill fiction metadata from committed EPG.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--budget", type=int, default=int(os.environ.get("BACKFILL_HTTP_BUDGET", "2500")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = root / "output"
    epg = output / "epg.xml.gz"
    mappings_path = output / "mapping.csv"

    tv = _load_epg(epg)
    mappings = _load_mappings(mappings_path)
    queue = build_queue(tv, mappings)
    before = queue_stats(root, queue)

    report = {
        "mode": "dry-run" if args.dry_run else "backfill",
        "total_unique": before.get("total_unique", 0),
        "before": before,
        "budget": max(0, args.budget),
    }

    if not args.dry_run:
        os.environ["METADATA_MAX_TITLES"] = str(max(20000, len(queue) + 100))
        os.environ["METADATA_MAX_HTTP_REQUESTS"] = str(max(0, args.budget))
        os.environ.setdefault("METADATA_DEADLINE_SECONDS", "2100")
        os.environ.setdefault("METADATA_TIMEOUT", "8")
        os.environ.setdefault("METADATA_CHECKPOINT_EVERY", "25")
        os.environ.setdefault("TMDB_EMPTY_PLAN_LIMIT", "4")

        result = enrich_metadata(tv, mappings, root, output)
        after = queue_stats(root, queue)
        summary = result.get("summary", {})
        report.update({
            "after": after,
            "remaining": after.get("remaining", 0),
            "with_overview": after.get("with_overview", 0),
            "with_genres": after.get("with_genres", 0),
            "http_spent": int(summary.get("metadata_http_requests_used", 0) or 0),
            "http_remaining": int(summary.get("metadata_http_requests_remaining", 0) or 0),
            "stopped_reason": summary.get("metadata_stopped_reason", "completed"),
            "metadata_summary": summary,
        })
    else:
        report.update({
            "remaining": before.get("remaining", 0),
            "with_overview": before.get("with_overview", 0),
            "with_genres": before.get("with_genres", 0),
            "http_spent": 0,
        })

    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "metadata-backfill.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
