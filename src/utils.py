from __future__ import annotations
import gzip, io, re, urllib.request, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UA = "IPTV-EPG-Builder/1.0"
QUALITY = re.compile(r"\b(?:uhd|fhd|hd|sd|4k|8k|hdr|hevc|h265|h\.265)\b", re.I)
PUNCT = re.compile(r"[^\w\d]+", re.UNICODE)

def normalize_name(value: str) -> str:
    s = (value or "").strip().lower().replace("ё", "е")
    s = QUALITY.sub(" ", s)
    s = PUNCT.sub(" ", s)
    return " ".join(s.split())

def is_real_tvg_id(value: str) -> bool:
    v = (value or "").strip().lower()
    if not v:
        return False
    collapsed = re.sub(r"[^a-z0-9]+", "", v)
    return not collapsed.startswith("noepg")

def fetch_bytes(url: str, timeout: int = 120, retries: int = 2) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")

def open_xml_bytes(data: bytes):
    if data[:2] == b"\x1f\x8b":
        return gzip.GzipFile(fileobj=io.BytesIO(data))
    return io.BytesIO(data)

def xmltv_date_is_fresh(timestamp: str, past_days: int = 2, future_days: int = 21) -> bool:
    if not timestamp or len(timestamp) < 8 or not timestamp[:8].isdigit():
        return False
    try:
        d = datetime.strptime(timestamp[:8], "%Y%m%d").date()
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=past_days) <= d <= today + timedelta(days=future_days)

def convert_xmltv_timestamp(timestamp: str, timezone_name: str) -> str:
    m = re.match(r"^(\d{8,14})\s*([+-]\d{4}|Z)(.*)$", (timestamp or "").strip())
    if not m:
        return timestamp
    digits, offset, tail = m.groups()
    fmt = {8: "%Y%m%d", 10: "%Y%m%d%H", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}.get(len(digits))
    if not fmt:
        return timestamp
    dt = datetime.strptime(digits, fmt)
    if offset == "Z":
        source_tz = timezone.utc
    else:
        sign = 1 if offset[0] == "+" else -1
        source_tz = timezone(sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5])))
    local = dt.replace(tzinfo=source_tz).astimezone(ZoneInfo(timezone_name))
    return local.strftime(fmt) + " " + local.strftime("%z") + tail
