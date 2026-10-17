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


def _parse_xmltv(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z", "%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _xmltv_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def _live_id(name: str) -> str:
    return "Xliveocr-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]


def _load_mapping(path: Path | None = None):
    path = path or MAPPING
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _save_mapping(fields, rows, path: Path | None = None):
    path = path or MAPPING
    if not fields:
        fields = [
            "playlist_name", "playlist_tvg_id", "output_tvg_id", "group",
            "region", "source", "source_id", "method", "confidence",
        ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _load_state(path: Path | None = None):
    path = path or STATE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_xml(path: Path | None = None):
    with gzip.open(path or EPG, "rb") as f:
        return ET.parse(f)


def _save_xml(tree, path: Path | None = None):
    path = path or EPG
    tmp = path.with_suffix(".xml.gz.tmp")
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
    tmp.replace(path)


def _has_real_current_programme(root: ET.Element, channel_id: str, at: datetime) -> bool:
    if not channel_id:
        return False
    for programme in root.findall("programme"):
        if programme.get("channel") != channel_id:
            continue
        if programme.get("x-live-ocr") == "1":
            continue
        start = _parse_xmltv(programme.get("start", ""))
        stop = _parse_xmltv(programme.get("stop", ""))
        if start and stop and start <= at < stop:
            return True
    return False


def _write_ocr_programme(root, channel_ids, tvg_id, name, title, start, stop):
    """3A write step: one current OCR programme per channel, other programmes untouched."""
    if tvg_id not in channel_ids:
        ch = ET.Element("channel", {"id": tvg_id})
        dn = ET.SubElement(ch, "display-name", {"lang": "ru"})
        dn.text = name
        root.insert(0, ch)
        channel_ids.add(tvg_id)

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
    skipped_existing_programme = []

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
        existing_tvg_id = (row or {}).get("output_tvg_id", "").strip()

        # Strict 3A rule: if a real current programme already exists, do nothing.
        # Wrong-programme channels belong to category 2 and are handled elsewhere.
        if existing_tvg_id and _has_real_current_programme(root, existing_tvg_id, observed_at):
            skipped_existing_programme.append(name)
            continue

        tvg_id = existing_tvg_id or _live_id(name)

        prev = state.get(name) if isinstance(state.get(name), dict) else {}
        same = _norm(prev.get("title", "")) == _norm(title)
        prev_seen = _parse_dt(prev.get("last_seen", "")) if prev else None

        if same and prev_seen and observed_at - prev_seen <= timedelta(hours=2):
            start = _parse_dt(prev.get("start", ""))
        else:
            start = observed_at

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
        elif not existing_tvg_id:
            row["output_tvg_id"] = tvg_id

        _write_ocr_programme(root, channel_ids, tvg_id, name, title, start, stop)

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

    print(json.dumps({
        "applied": len(selected),
        "channels": selected,
        "skipped_existing_programme": skipped_existing_programme,
    }, ensure_ascii=False))
    return 0


def _parse_iso_or_none(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def apply_state(
    now: datetime | None = None,
    *,
    epg_path: Path | None = None,
    uhf_path: Path | None = None,
    mapping_path: Path | None = None,
    state_path: Path | None = None,
) -> dict:
    """Stage 1b: Update EPG re-applies still-valid 3A observations after the main build.

    Rules:
    - the channel ID is resolved by playlist name from the CURRENT build
      (uhf-mapping.json, then mapping.csv); the ID stored in the state is never
      trusted, so an old Xliveocr-* ID cannot duplicate a channel that has since
      got a real binding;
    - nothing is applied when the channel has a real (non-OCR) current programme;
    - expired or malformed observations are ignored;
    - real programmes are never removed or changed: the OCR window is clipped so it
      does not overlap them;
    - the state file is read only (it belongs to Verify Missing Movie EPG).
    """
    epg_path = epg_path or EPG
    uhf_path = uhf_path or UHF
    mapping_path = mapping_path or MAPPING
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    report = {"applied": 0, "channels": [], "expired": 0, "invalid": 0, "skipped_real_programme": 0, "skipped_no_window": 0}
    state = _load_state(state_path)
    if not state:
        report["reason"] = "no-state"
        return report
    if not epg_path.exists():
        report["reason"] = "epg-missing"
        return report

    uhf = {}
    if uhf_path.exists():
        try:
            uhf = json.loads(uhf_path.read_text(encoding="utf-8"))
        except Exception:
            uhf = {}
    if not isinstance(uhf, dict):
        uhf = {}
    uhf_channels = uhf.get("channels") if isinstance(uhf.get("channels"), dict) else {}
    fields, mappings = _load_mapping(mapping_path)
    by_name = {(r.get("playlist_name") or "").strip(): r for r in mappings}

    tree = _load_xml(epg_path)
    root = tree.getroot()
    channel_ids = {c.get("id", "") for c in root.findall("channel")}
    real = {}
    for programme in root.findall("programme"):
        if programme.get("x-live-ocr") == "1":
            continue
        start = _parse_xmltv(programme.get("start", ""))
        stop = _parse_xmltv(programme.get("stop", ""))
        if start and stop:
            real.setdefault(programme.get("channel", ""), []).append((start, stop))

    new_uhf = {}
    mapping_changed = False
    for raw_name, entry in state.items():
        name = (raw_name or "").strip()
        if not isinstance(entry, dict) or not name:
            report["invalid"] += 1
            continue
        title = str(entry.get("title") or "").strip()
        start = _parse_iso_or_none(entry.get("start"))
        stop = _parse_iso_or_none(entry.get("stop"))
        if not title or start is None or stop is None:
            report["invalid"] += 1
            continue
        if stop <= now:
            report["expired"] += 1
            continue

        tvg_id = (
            str(uhf_channels.get(name) or "").strip()
            or (by_name.get(name) or {}).get("output_tvg_id", "").strip()
            or _live_id(name)
        )
        windows = real.get(tvg_id, [])
        if any(s <= now < e for s, e in windows):
            report["skipped_real_programme"] += 1
            continue
        start = min(start, now)
        for s, e in windows:
            if e <= now and e > start:
                start = e
            if s > now and s < stop:
                stop = s
        if not start < stop or stop <= now:
            report["skipped_no_window"] += 1
            continue

        _write_ocr_programme(root, channel_ids, tvg_id, name, title, start, stop)
        if name not in uhf_channels:
            new_uhf[name] = tvg_id
        if name not in by_name:
            row = {field: "" for field in fields}
            row.update({
                "playlist_name": name,
                "output_tvg_id": tvg_id,
                "source": "live-ocr",
                "source_id": tvg_id,
                "method": "live-ocr-current",
                "confidence": "95",
            })
            mappings.append(row)
            by_name[name] = row
            mapping_changed = True
        report["channels"].append({"playlist_name": name, "tvg_id": tvg_id, "title": title})

    report["applied"] = len(report["channels"])
    if report["applied"]:
        _save_xml(tree, epg_path)
        if new_uhf:
            uhf.setdefault("channels", {})
            if not isinstance(uhf["channels"], dict):
                uhf["channels"] = {}
            uhf["channels"].update(new_uhf)
            uhf_path.write_text(json.dumps(uhf, ensure_ascii=False, indent=2), encoding="utf-8")
        if mapping_changed:
            _save_mapping(fields, mappings, mapping_path)
    return report


if __name__ == "__main__":
    raise SystemExit(main())
