from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def is_ditv_channel(name: str) -> bool:
    return bool(re.match(r"^DITV\b", (name or "").strip(), flags=re.IGNORECASE))


def ditv_id(name: str) -> str:
    """Stable synthetic XMLTV id for a DITV channel name."""
    normalized = re.sub(r"\s+", " ", (name or "").strip().casefold())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"ditv-{digest}"


def _xmltv_ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S %z")


def build_ditv_fallback(name: str, timezone_name: str, *, now: datetime | None = None):
    """Create honest fallback XMLTV metadata for one DITV stream.

    This intentionally does NOT invent film/episode titles.  It only provides
    a rolling generic on-air block so players no longer display "No programme".
    A real upstream XMLTV match must always win before this fallback is used.
    """
    tz = ZoneInfo(timezone_name)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    channel_id = ditv_id(name)
    channel = ET.Element("channel", {"id": channel_id})
    dn = ET.SubElement(channel, "display-name")
    dn.text = name

    # Start before "now" so a current programme is always present.  Use
    # four-hour blocks for the next eight days; this is deliberately generic.
    start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=4)
    programmes = []
    for n in range(2 * 24 * 8 // 8 + 1):
        # 4-hour blocks: 6 per day, eight days + a little lookback.
        block_start = start + timedelta(hours=4 * n)
        block_stop = block_start + timedelta(hours=4)
        p = ET.Element("programme", {
            "channel": channel_id,
            "start": _xmltv_ts(block_start),
            "stop": _xmltv_ts(block_stop),
        })
        title = ET.SubElement(p, "title", {"lang": "ru"})
        title.text = f"{name} — эфир"
        desc = ET.SubElement(p, "desc", {"lang": "ru"})
        desc.text = (
            "Резервная программа DITV. Точное поэпизодное расписание каналом "
            "не опубликовано; при появлении проверенного XMLTV этот fallback "
            "автоматически перестанет использоваться."
        )
        programmes.append(p)

    return channel_id, channel, programmes
