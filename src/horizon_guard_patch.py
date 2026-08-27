"""Prevent short-horizon XMLTV feeds from winning a channel permanently.

The builder runs every 6 hours. A source must normally publish at least
EPG_MIN_FUTURE_HOURS (default 12) beyond the current time for a channel to be
eligible for matching. Short/stale candidates are filtered from source.channels
so later sources can win automatically. If every source is short, the channel is
left unmatched rather than publishing an EPG that will expire before the next
normal update cycle.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from . import xmltv as _xmltv
from .utils import parse_xmltv_datetime, open_xml_bytes

PATCH_VERSION = "14.12-horizon-guard"
DEFAULT_MIN_FUTURE_HOURS = 12.0
_ORIGINAL_INDEX = _xmltv.XMLTVSource.index


def _min_future_hours() -> float:
    raw = os.environ.get("EPG_MIN_FUTURE_HOURS", str(DEFAULT_MIN_FUTURE_HOURS))
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_MIN_FUTURE_HOURS


def _programme_horizons(source) -> dict[str, float]:
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
    return {cid: (dt - now).total_seconds() / 3600.0 for cid, dt in max_end.items()}


def guarded_index(self):
    result = _ORIGINAL_INDEX(self)
    min_hours = _min_future_hours()
    if min_hours <= 0 or not result.channels:
        result.horizon_hours_by_id = {}
        return result

    horizons = _programme_horizons(result)
    result.horizon_hours_by_id = horizons
    before = set(result.channels)
    eligible = {cid for cid in before if horizons.get(cid, -1e9) >= min_hours}
    deferred = before - eligible

    if deferred:
        result.channels = {cid: elem for cid, elem in result.channels.items() if cid in eligible}
        result.usable_ids.intersection_update(eligible)
        result.names = {
            name: (ids & eligible)
            for name, ids in result.names.items()
            if ids & eligible
        }
        print(
            f"[{result.name}] horizon-guard deferred={len(deferred)} "
            f"eligible={len(eligible)} min_future_hours={min_hours:g}",
            flush=True,
        )
    return result


_xmltv.XMLTVSource.index = guarded_index
