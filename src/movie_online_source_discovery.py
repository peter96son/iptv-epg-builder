"""Find exact-name EPG candidates for missing movie channels without OCR.

This is deliberately a discovery report, not an auto-binding tool. A matching
display name is evidence to investigate; independent schedule agreement is
reported separately and still needs a live/provider check before selection.
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import load_sources
from .source_evidence import _norm as normalize_title
from .utils import fetch_bytes, normalize_name, parse_xmltv_datetime
from .xmltv import XMLTVSource

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
GAPS = OUTPUT / "movie-epg-gaps.csv"
REPORT = OUTPUT / "movie-online-source-discovery.json"
TARGET_GROUPS = {"Кино", "USSR", "Кинозалы", "Кино 4K"}


def _missing_channels(path: Path | None = None) -> list[dict]:
    path = path or GAPS
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # Audit files can be either a gaps-only list or the full channel audit.
    channels = {}
    for row in rows:
        name = (row.get("playlist_name") or row.get("provider_name") or "").strip()
        if not name or row.get("group") not in TARGET_GROUPS:
            continue
        if row.get("status", "NO_MAPPING") == "OK":
            continue
        key = normalize_name(name)
        if not key:
            continue
        target = channels.setdefault(key, {
            "group": row.get("group", ""),
            "playlist_name": name,
            "provider_name": (row.get("provider_name") or "").strip(),
            "provider_tvg_id": (row.get("provider_tvg_id") or "").strip(),
        })
        if not target["provider_name"]:
            target["provider_name"] = (row.get("provider_name") or "").strip()
    return list(channels.values())


def _channel_names(elem) -> list[str]:
    return [
        child.text.strip()
        for child in elem
        if child.tag.split("}")[-1] == "display-name" and child.text and child.text.strip()
    ]


def _programme_data(programme: dict) -> dict:
    title = ""
    for child in programme:
        if child.tag.split("}")[-1] == "title" and child.text and child.text.strip():
            title = child.text.strip()
            break
    start = parse_xmltv_datetime(programme.get("start", ""))
    stop = parse_xmltv_datetime(programme.get("stop", ""))
    if start is not None:
        start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)
    if stop is not None:
        stop = stop.replace(tzinfo=timezone.utc) if stop.tzinfo is None else stop.astimezone(timezone.utc)
    return {"title": title, "start": start, "stop": stop}


def _scan_source(spec: tuple, channels: list[dict], now: datetime, timeout: int) -> dict:
    index, config = spec
    source = str(config.get("name") or config.get("id") or f"source-{index}")
    url = str(config.get("url") or config.get("xmltv") or config.get("epg_url") or "")
    xml = None
    try:
        payload = fetch_bytes(url, timeout=timeout, retries=1, stale_if_error_seconds=0)
        xml = XMLTVSource(source, payload).index()
        matches = []
        wanted = set()
        targets_by_norm = defaultdict(list)
        for target in channels:
            for label in (target["playlist_name"], target["provider_name"]):
                norm = normalize_name(label)
                if norm:
                    targets_by_norm[norm].append(target)
        for source_id, elem in xml.channels.items():
            display_names = _channel_names(elem)
            source_labels = {normalize_name(source_id), *(normalize_name(n) for n in display_names)}
            target_matches = {}
            for source_label in source_labels:
                if source_label:
                    for target in targets_by_norm.get(source_label, []):
                        target_matches[target["playlist_name"]] = target
            if not target_matches:
                continue
            wanted.add(source_id)
            for target in target_matches.values():
                matches.append({
                    "playlist_name": target["playlist_name"],
                    "group": target["group"],
                    "source_id": source_id,
                    "display_names": display_names,
                    "programme": None,
                })
        by_id = defaultdict(list)
        for match in matches:
            by_id[match["source_id"]].append(match)
        for programme in xml.fresh_programmes(wanted, past_days=0, future_days=2):
            sid = (programme.get("channel") or "").strip()
            if sid not in by_id:
                continue
            item = _programme_data(programme)
            if not item["title"] or item["start"] is None:
                continue
            for match in by_id[sid]:
                existing = match["programme"]
                active = item["start"] <= now and (item["stop"] is None or now < item["stop"])
                existing_active = bool(existing and existing.get("is_current"))
                if active or existing is None or (not existing_active and item["start"] < existing["_start"]):
                    match["programme"] = {
                        "title": item["title"],
                        "start": item["start"].isoformat(),
                        "stop": item["stop"].isoformat() if item["stop"] else None,
                        "is_current": active,
                        "_start": item["start"],
                    }
        for match in matches:
            if match["programme"]:
                match["programme"].pop("_start", None)
        host = (urlparse(url).hostname or "").casefold()
        return {"source": source, "family": str(config.get("consensus_family") or host or source).casefold(), "matches": matches}
    except Exception as exc:
        return {"source": source, "error": type(exc).__name__, "matches": []}
    finally:
        if xml is not None:
            xml.release()


def run() -> dict:
    channels = _missing_channels()
    now = datetime.now(timezone.utc)
    timeout = max(8, min(45, int(os.environ.get("EPG_ONLINE_DISCOVERY_TIMEOUT", "20"))))
    workers = max(1, min(8, int(os.environ.get("EPG_ONLINE_DISCOVERY_WORKERS", "6"))))
    if not channels:
        payload = {
            "generated_at": now.isoformat(),
            "method": "exact normalized channel display-name matching; current programme comparison; one vote per feed host family",
            "automatic_binding": False,
            "sources_scanned": 0,
            "sources_failed": [],
            "channels": {},
        }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        temp = REPORT.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(REPORT)
        print(json.dumps({"sources_scanned": 0, "sources_failed": 0, "channels": 0, "report": str(REPORT)}, ensure_ascii=False), flush=True)
        return payload
    configs = []
    for i, config in enumerate(load_sources()):
        if not config.get("enabled", True):
            continue
        groups = set(config.get("groups") or [])
        if groups and not groups.intersection(TARGET_GROUPS):
            continue
        if config.get("url") or config.get("xmltv") or config.get("epg_url"):
            configs.append((i, config))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_scan_source, spec, channels, now, timeout) for spec in configs]
        for future in as_completed(futures):
            results.append(future.result())

    by_channel = {}
    for target in channels:
        per_family = {}
        for result in results:
            if result.get("error"):
                continue
            for match in result["matches"]:
                if match["playlist_name"] != target["playlist_name"]:
                    continue
                old = per_family.get(result["family"])
                candidate = {"source": result["source"], "family": result["family"], **match}
                # Multiple feeds from the same host family count as one vote.
                if old is None or (candidate["programme"] or {}).get("is_current", False):
                    per_family[result["family"]] = candidate
        votes = defaultdict(list)
        for candidate in per_family.values():
            programme = candidate.get("programme") or {}
            title = programme.get("title") or ""
            norm = normalize_title(title) if title else ""
            if norm and programme.get("is_current"):
                votes[norm].append(candidate)
        ordered = sorted(votes.items(), key=lambda item: (-len(item[1]), item[0]))
        _, top = ordered[0] if ordered else ("", [])
        total = len(per_family)
        majority = len(top) >= 2 and len(top) * 2 > total
        by_channel[target["playlist_name"]] = {
            **target,
            "status": "SOURCE_CONSENSUS_UNVERIFIED" if majority else (
                "SOURCE_DISAGREEMENT_UNVERIFIED" if len(votes) > 1 else
                "SINGLE_SOURCE_CANDIDATE" if total == 1 else
                "NO_CURRENT_SCHEDULE" if total else "NO_EXACT_NAME_MATCH"
            ),
            "independent_sources": total,
            "consensus_votes": len(top),
            "current_title": top[0]["programme"]["title"] if top else "",
            "sources": [
                {k: candidate[k] for k in ("source", "family", "source_id", "display_names", "programme")}
                for candidate in sorted(per_family.values(), key=lambda c: (c["source"], c["source_id"]))
            ],
            "outliers": [
                {"source": c["source"], "family": c["family"], "source_id": c["source_id"], "title": (c.get("programme") or {}).get("title", "")}
                for _, group in ordered[1:] for c in group
            ] if majority else [],
        }
    payload = {
        "generated_at": now.isoformat(),
        "method": "exact normalized channel display-name matching; current programme comparison; one vote per feed host family",
        "automatic_binding": False,
        "sources_scanned": len(results),
        "sources_failed": [{"source": r["source"], "error": r["error"]} for r in results if r.get("error")],
        "channels": by_channel,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(REPORT)
    summary = defaultdict(int)
    for row in by_channel.values():
        summary[row["status"]] += 1
    print(json.dumps({"sources_scanned": len(results), "sources_failed": len(payload["sources_failed"]), "channels": len(channels), "status_counts": dict(summary), "report": str(REPORT)}, ensure_ascii=False), flush=True)
    return payload


if __name__ == "__main__":
    run()
