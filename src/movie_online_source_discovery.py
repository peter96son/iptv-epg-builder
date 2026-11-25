"""Check whether EPG feeds cover movie channels that currently lack schedules.

The report is coverage evidence only. A channel-name match never changes a
binding, and programme titles are deliberately not compared here.
"""
from __future__ import annotations

import csv
import json
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import load_sources
from .utils import fetch_bytes, normalize_name, open_xml_bytes, parse_xmltv_datetime

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
GAPS = OUTPUT / "movie-epg-gaps.csv"
CANDIDATES = ROOT / "data" / "online_epg_candidates.json"
REPORT = OUTPUT / "movie-online-source-discovery.json"
TARGET_GROUPS = {"Кино", "USSR", "Кинозалы", "Кино 4K"}


def _missing_channels(path: Path | None = None) -> list[dict]:
    """Read target-group channels that have no usable programme mapping."""
    path = path or GAPS
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
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
        channels.setdefault(key, {
            "group": row.get("group", ""),
            "playlist_name": name,
            "provider_name": (row.get("provider_name") or "").strip(),
            "provider_tvg_id": (row.get("provider_tvg_id") or "").strip(),
        })
    return list(channels.values())


def _channel_names(elem) -> list[str]:
    return [
        child.text.strip()
        for child in elem
        if child.tag.split("}")[-1] == "display-name" and child.text and child.text.strip()
    ]


def _source_inventory() -> list[dict]:
    """Combine configured feeds with the user's candidate list, de-duping URLs."""
    rows = []
    seen_urls = set()
    for config in load_sources():
        if not config.get("enabled", True):
            continue
        groups = set(config.get("groups") or [])
        if groups and not groups.intersection(TARGET_GROUPS):
            continue
        url = str(config.get("url") or config.get("xmltv") or config.get("epg_url") or "").strip()
        if not url:
            continue
        seen_urls.add(url.rstrip("/"))
        rows.append({"name": str(config.get("name") or urlparse(url).hostname or "feed"), "url": url, "kind": "configured"})

    try:
        candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    except FileNotFoundError:
        candidates = []
    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        key = url.rstrip("/")
        if not url or key in seen_urls:
            continue
        seen_urls.add(key)
        rows.append({"name": candidate["name"], "url": url, "kind": "candidate"})
    return rows


def _scan_source(spec: tuple, channels: list[dict], now: datetime, timeout: int) -> dict:
    index, source = spec
    name, url, kind = source["name"], source["url"], source["kind"]
    try:
        payload = fetch_bytes(url, timeout=timeout, retries=0, stale_if_error_seconds=0)
        targets_by_norm = defaultdict(list)
        for target in channels:
            for label in (target["playlist_name"], target["provider_name"]):
                norm = normalize_name(label)
                if norm:
                    targets_by_norm[norm].append(target)

        matches = {}
        by_source_id = defaultdict(list)
        horizon = now + timedelta(days=7)
        stream = open_xml_bytes(payload)
        try:
            context = ET.iterparse(stream, events=("start", "end"))
            _, root = next(context)
            for event, elem in context:
                if event != "end":
                    continue
                tag = elem.tag.split("}")[-1]
                if tag == "channel":
                    source_id = (elem.get("id") or "").strip()
                    display_names = _channel_names(elem)
                    labels = {normalize_name(source_id), *(normalize_name(label) for label in display_names)}
                    targets = {}
                    for label in labels:
                        if label:
                            for target in targets_by_norm.get(label, []):
                                targets[target["playlist_name"]] = target
                    for target in targets.values():
                        match = {
                            "playlist_name": target["playlist_name"],
                            "group": target["group"],
                            "source_id": source_id,
                            "display_names": display_names,
                            "programmes_7d": 0,
                        }
                        matches[(target["playlist_name"], source_id)] = match
                        by_source_id[source_id].append(match)
                    elem.clear()
                    root.clear()
                elif tag == "programme":
                    source_id = (elem.get("channel") or "").strip()
                    if source_id in by_source_id:
                        has_title = any(
                            child.tag.split("}")[-1] == "title" and child.text and child.text.strip()
                            for child in elem
                        )
                        start = parse_xmltv_datetime(elem.get("start", ""))
                        stop = parse_xmltv_datetime(elem.get("stop", ""))
                        if start is not None:
                            start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)
                        if stop is not None:
                            stop = stop.replace(tzinfo=timezone.utc) if stop.tzinfo is None else stop.astimezone(timezone.utc)
                        if has_title and start is not None and now <= start <= horizon and (stop is None or stop > start):
                            for match in by_source_id[source_id]:
                                match["programmes_7d"] += 1
                    elem.clear()
                    root.clear()
        finally:
            stream.close()
        return {
            "source": name,
            "url": url,
            "kind": kind,
            "family": (urlparse(url).hostname or name).casefold(),
            "matches": list(matches.values()),
        }
    except Exception as exc:
        return {"source": name, "url": url, "kind": kind, "error": type(exc).__name__, "matches": []}


def run() -> dict:
    channels = _missing_channels()
    now = datetime.now(timezone.utc)
    timeout = max(5, min(30, int(os.environ.get("EPG_ONLINE_DISCOVERY_TIMEOUT", "12"))))
    workers = max(1, min(12, int(os.environ.get("EPG_ONLINE_DISCOVERY_WORKERS", "10"))))
    sources = _source_inventory() if channels else []
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_scan_source, spec, channels, now, timeout) for spec in enumerate(sources)]
        for future in as_completed(futures):
            results.append(future.result())

    source_rows = []
    channel_rows = {target["playlist_name"]: {**target, "sources_with_channel": [], "sources_with_7d_schedule": []} for target in channels}
    for result in sorted(results, key=lambda item: item["source"]):
        matches = result.get("matches", [])
        for match in matches:
            row = {
                "source": result["source"],
                "family": result["family"],
                "source_id": match["source_id"],
                "display_names": match["display_names"],
                "programmes_7d": match["programmes_7d"],
            }
            channel = channel_rows[match["playlist_name"]]
            channel["sources_with_channel"].append(row)
            if match["programmes_7d"] > 0:
                channel["sources_with_7d_schedule"].append(row)
        source_rows.append({
            "source": result["source"],
            "url": result["url"],
            "kind": result["kind"],
            "family": result.get("family", ""),
            "status": "ERROR" if result.get("error") else "OK",
            "error": result.get("error", ""),
            "channels_found": len({m["playlist_name"] for m in matches}),
            "channels_with_7d_schedule": len({m["playlist_name"] for m in matches if m["programmes_7d"] > 0}),
            "channels": matches,
        })

    payload = {
        "generated_at": now.isoformat(),
        "method": "normalized exact channel-name coverage; counts programmes scheduled within the next 7 days",
        "scope": sorted(TARGET_GROUPS),
        "automatic_binding": False,
        "programme_title_comparison": False,
        "sources_scanned": len(results),
        "sources_failed": [{"source": r["source"], "url": r["url"], "error": r["error"]} for r in results if r.get("error")],
        "sources": source_rows,
        "channels_without_provider_schedule": list(channel_rows.values()),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(REPORT)
    print(json.dumps({
        "sources_scanned": len(results),
        "sources_failed": len(payload["sources_failed"]),
        "provider_missing_channels": len(channels),
        "covered_by_online_source": sum(bool(row["sources_with_7d_schedule"]) for row in channel_rows.values()),
        "report": str(REPORT),
    }, ensure_ascii=False), flush=True)
    return payload


if __name__ == "__main__":
    run()
