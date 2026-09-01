"""v15 source horizon observer.

XMLTVSource.index() already excludes channels with no current/upcoming usable
programmes. v14.12 additionally removed channels merely because their future
window was shorter than N hours. That caused valid rolling EPGs (4ever and
Premiere Group among them) to disappear.

v15 never removes an otherwise usable source channel for a short horizon.
It records the horizon for diagnostics and lets source-chain priority decide
which provider wins.
"""
from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from . import xmltv as _xmltv
from .utils import parse_xmltv_datetime, open_xml_bytes

PATCH_VERSION = "15.0-source-chain-stability"
DEFAULT_MIN_FUTURE_HOURS = 6.0
_ORIGINAL_INDEX = _xmltv.XMLTVSource.index

def _min_future_hours() -> float:
    raw = os.environ.get("EPG_MIN_FUTURE_HOURS", str(DEFAULT_MIN_FUTURE_HOURS))
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_MIN_FUTURE_HOURS

def _programme_horizons(source):
    now = datetime.now(timezone.utc)
    max_end = {}
    f = source._open() if hasattr(source, "_open") else open_xml_bytes(source.data)
    try:
        context = ET.iterparse(f, events=("start", "end"))
        try:
            _, root = next(context)
        except StopIteration:
            return {}
        for event, elem in context:
            if event != "end":
                continue
            if elem.tag.split("}")[-1] == "programme":
                cid = elem.get("channel", "")
                if cid:
                    if hasattr(source, "_shifted_timestamp"):
                        stop = source._shifted_timestamp(cid, elem.get("stop", ""))
                        start = source._shifted_timestamp(cid, elem.get("start", ""))
                    else:
                        stop = elem.get("stop", "")
                        start = elem.get("start", "")
                    dt = parse_xmltv_datetime(stop) or parse_xmltv_datetime(start)
                    if dt is not None and (cid not in max_end or dt > max_end[cid]):
                        max_end[cid] = dt
                elem.clear()
                root.clear()
    finally:
        f.close()
    return {cid: (dt-now).total_seconds()/3600.0 for cid, dt in max_end.items()}

def observed_index(self):
    result = _ORIGINAL_INDEX(self)
    horizons = _programme_horizons(result) if result.channels else {}
    result.horizon_hours_by_id = horizons
    min_hours = _min_future_hours()
    result.short_horizon_ids = {
        cid for cid in result.channels if horizons.get(cid, -1e9) < min_hours
    }
    if result.short_horizon_ids:
        print(
            f"[{result.name}] horizon-warning short={len(result.short_horizon_ids)} "
            f"usable={len(result.channels)} threshold={min_hours:g}h; kept for fallback",
            flush=True,
        )
    return result

_xmltv.XMLTVSource.index = observed_index
