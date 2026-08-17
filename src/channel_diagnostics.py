from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from .utils import parse_xmltv_datetime
from .state import save_json


def load_watchlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("channels", [])
    if not isinstance(payload, list):
        return []
    return [str(x).strip() for x in payload if str(x).strip()]


def _programme_row(elem: ET.Element) -> dict:
    title = elem.findtext("title") or ""
    desc = elem.findtext("desc") or ""
    category = [x.text or "" for x in elem.findall("category") if (x.text or "").strip()]
    return {
        "start": elem.get("start", ""),
        "stop": elem.get("stop", ""),
        "title": title,
        "description": desc,
        "categories": category,
    }


def build_channel_diagnostics(
    tv: ET.Element,
    mappings: list[dict],
    watchlist: list[str],
    output_path: Path,
    *,
    generated_at: str = "",
) -> dict:
    now = datetime.now(timezone.utc)
    mapping_by_name = {row.get("playlist_name", ""): row for row in mappings}
    programmes_by_id: dict[str, list[ET.Element]] = {}
    for elem in tv.findall("programme"):
        cid = elem.get("channel", "")
        if cid:
            programmes_by_id.setdefault(cid, []).append(elem)

    channels = []
    for name in watchlist:
        mapping = mapping_by_name.get(name)
        if not mapping:
            channels.append({
                "playlist_name": name,
                "matched": False,
                "status": "not_mapped",
            })
            continue

        out_id = mapping.get("output_tvg_id", "")
        elems = programmes_by_id.get(out_id, [])
        parsed = []
        for elem in elems:
            start_dt = parse_xmltv_datetime(elem.get("start", ""))
            stop_dt = parse_xmltv_datetime(elem.get("stop", "")) if elem.get("stop") else None
            if start_dt is None:
                continue
            parsed.append((start_dt, stop_dt, elem))
        parsed.sort(key=lambda x: x[0])

        current = None
        upcoming = []
        for start_dt, stop_dt, elem in parsed:
            if start_dt <= now and (stop_dt is None or now < stop_dt):
                current = _programme_row(elem)
            elif start_dt > now and len(upcoming) < 8:
                upcoming.append(_programme_row(elem))

        channels.append({
            "playlist_name": name,
            "matched": True,
            "status": "ok" if (current or upcoming) else "no_current_or_upcoming_programme",
            "output_tvg_id": out_id,
            "group": mapping.get("group", ""),
            "region": mapping.get("region", ""),
            "source": mapping.get("source", ""),
            "source_id": mapping.get("source_id", ""),
            "method": mapping.get("method", ""),
            "programme_count": len(elems),
            "parseable_programme_count": len(parsed),
            "current_programme": current,
            "upcoming_programmes": upcoming,
        })

    payload = {
        "generated_at": generated_at,
        "watchlist_channels": len(watchlist),
        "channels": channels,
    }
    save_json(output_path, payload)
    return payload
