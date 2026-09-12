from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
PROBE = OUTPUT / "movie-gap-live-probe.json"
MAPPING = OUTPUT / "mapping.csv"
UHF = OUTPUT / "uhf-mapping.json"
EPG = OUTPUT / "epg.xml.gz"
STATE = ROOT / "data" / "live_ocr_epg_state.json"

ALLOWED_GAPS = {"NO_MAPPING", "NO_CURRENT_PROGRAMME"}


def _norm(value: str) -> str:
    s = (value or "").casefold().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9]+", " ", s)
    return " ".join(s.split())


def _parse_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _xmltv_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def _live_id(name: str) -> str:
    return "Xliveocr-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]


def _load_mapping():
    if not MAPPING.exists():
        return [], []
    with MAPPING.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _save_mapping(fields, rows):
    if not fields:
        fields = [
            "playlist_name", "playlist_tvg_id", "output_tvg_id", "group",
            "region", "source", "source_id", "method", "confidence",
        ]
    with MAPPING.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _load_state():
    if not STATE.exists():
        return {}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_xml():
    with gzip.open(EPG, "rb") as f:
        return ET.parse(f)


def _save_xml(tree):
    tmp = EPG.with_suffix(".xml.gz.tmp")
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
    tmp.replace(EPG)


def main() -> int:
    if not PROBE.exists() or not EPG.exists():
        print(json.dumps({"applied": 0, "reason": "probe-or-epg-missing"}))
        return 0

    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    observed_at = _parse_dt(probe.get("generated_at", ""))
    fields, mappings = _load_mapping()
    by_name = {(r.get("playlist_name") or "").strip(): r for r in mappings}
    state = _load_state()

    tree = _load_xml()
    root = tree.getroot()
    channel_ids = {c.get("id", "") for c in root.findall("channel")}
    selected = []

    for item in (probe.get("channels") or {}).values():
        if not isinstance(item, dict):
            continue
        title_info = item.get("recognized_title") or {}
        if title_info.get("confidence") != "high":
            continue

        status = (item.get("gap_status") or "").strip()
        if not any(flag in status for flag in ALLOWED_GAPS):
            continue

        name = (item.get("playlist_name") or "").strip()
        title = (title_info.get("title") or "").strip()
        if not name or not title:
            continue

        row = by_name.get(name)
        tvg_id = (row or {}).get("output_tvg_id", "").strip() or _live_id(name)

        prev = state.get(name) if isinstance(state.get(name), dict) else {}
        same = _norm(prev.get("title", "")) == _norm(title)
        prev_seen = _parse_dt(prev.get("last_seen", "")) if prev else None

        if same and prev_seen and observed_at - prev_seen <= timedelta(hours=2):
            start = _parse_dt(prev.get("start", ""))
        else:
            start = observed_at

        # Current-title overlay is deliberately short-lived. It is refreshed hourly.
        stop = observed_at + timedelta(minutes=70)

        if row is None:
            row = {field: "" for field in fields}
            row.update({
                "playlist_name": name,
                "playlist_tvg_id": (item.get("provider_tvg_id") or "").strip(),
                "output_tvg_id": tvg_id,
                "group": (item.get("group") or "").strip(),
                "source": "live-ocr",
                "source_id": tvg_id,
                "method": "live-ocr-current",
                "confidence": "95",
            })
            mappings.append(row)
            by_name[name] = row
        elif not (row.get("output_tvg_id") or "").strip():
            row["output_tvg_id"] = tvg_id

        if tvg_id not in channel_ids:
            ch = ET.Element("channel", {"id": tvg_id})
            dn = ET.SubElement(ch, "display-name", {"lang": "ru"})
            dn.text = name
            root.insert(0, ch)
            channel_ids.add(tvg_id)

        # Remove only our previous synthetic entries for this channel.
        for programme in list(root.findall("programme")):
            if programme.get("channel") == tvg_id and programme.get("x-live-ocr") == "1":
                root.remove(programme)

        programme = ET.Element("programme", {
            "start": _xmltv_dt(start),
            "stop": _xmltv_dt(stop),
            "channel": tvg_id,
            "x-live-ocr": "1",
        })
        t = ET.SubElement(programme, "title", {"lang": "ru"})
        t.text = title
        c = ET.SubElement(programme, "category", {"lang": "ru"})
        c.text = "Кино"
        root.append(programme)

        state[name] = {
            "title": title,
            "tvg_id": tvg_id,
            "start": start.isoformat(),
            "last_seen": observed_at.isoformat(),
            "stop": stop.isoformat(),
            "confidence": title_info.get("score"),
        }
        selected.append({"playlist_name": name, "title": title, "tvg_id": tvg_id})

    if selected:
        _save_mapping(fields, mappings)
        _save_xml(tree)

        uhf = {}
        if UHF.exists():
            try:
                uhf = json.loads(UHF.read_text(encoding="utf-8"))
            except Exception:
                uhf = {}
        if not isinstance(uhf, dict):
            uhf = {}
        channels = uhf.setdefault("channels", {})
        if not isinstance(channels, dict):
            channels = {}
            uhf["channels"] = channels
        for item in selected:
            channels[item["playlist_name"]] = item["tvg_id"]
        uhf["generated_at"] = datetime.now(timezone.utc).isoformat()
        UHF.write_text(json.dumps(uhf, ensure_ascii=False, indent=2), encoding="utf-8")

        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"applied": len(selected), "channels": selected}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
