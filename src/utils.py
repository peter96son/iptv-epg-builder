from __future__ import annotations
import gzip, io, re, urllib.request, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UA = "IPTV-EPG-Builder/1.1.1"
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
        year = int(timestamp[0:4])
        month = int(timestamp[4:6])
        day = int(timestamp[6:8])
        d = datetime(year, month, day).date()
    except (ValueError, TypeError):
        return False
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=past_days) <= d <= today + timedelta(days=future_days)

def _parse_xmltv_digits(digits: str) -> datetime:
    if len(digits) not in (8, 10, 12, 14) or not digits.isdigit():
        raise ValueError("unsupported XMLTV timestamp precision")

    year = int(digits[0:4])
    month = int(digits[4:6])
    day = int(digits[6:8])
    hour = int(digits[8:10]) if len(digits) >= 10 else 0
    minute = int(digits[10:12]) if len(digits) >= 12 else 0
    second = int(digits[12:14]) if len(digits) >= 14 else 0

    next_day = False
    if hour == 24 and minute == 0 and second == 0:
        hour = 0
        next_day = True

    leap_second = second == 60
    if leap_second:
        second = 59

    dt = datetime(year, month, day, hour, minute, second)
    if next_day:
        dt += timedelta(days=1)
    if leap_second:
        dt += timedelta(seconds=1)
    return dt



def parse_xmltv_datetime(timestamp: str):
    """Parse a standard XMLTV timestamp to an aware datetime in UTC.

    Returns None for malformed/non-standard values; callers must fail closed.
    Supports XMLTV precisions YYYYMMDD through YYYYMMDDhhmmss plus Z/+HHMM.
    """
    raw = (timestamp or "").strip()
    m = re.match(r"^(\d{8}|\d{10}|\d{12}|\d{14})\s*([+-]\d{4}|Z)", raw)
    if not m:
        return None
    digits, offset = m.groups()
    try:
        dt = _parse_xmltv_digits(digits)
        if offset == "Z":
            source_tz = timezone.utc
        else:
            sign = 1 if offset[0] == "+" else -1
            hours = int(offset[1:3])
            minutes = int(offset[3:5])
            if hours > 23 or minutes > 59:
                return None
            source_tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
        return dt.replace(tzinfo=source_tz).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def xmltv_programme_is_usable(
    start: str,
    stop: str = "",
    *,
    now=None,
    lookback_hours: int = 6,
    future_hours: int = 48,
) -> bool:
    """Return True when a programme makes the guide useful now or soon.

    We allow a small lookback because some XMLTV feeds have imperfect stop
    times, but a channel with only old programmes is no longer treated as
    covered.  A future programme up to 48h ahead is enough to keep the source
    eligible and lets the player show Next/Upcoming data.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    start_dt = parse_xmltv_datetime(start)
    if start_dt is None:
        return False
    stop_dt = parse_xmltv_datetime(stop) if stop else None

    window_start = now - timedelta(hours=lookback_hours)
    window_end = now + timedelta(hours=future_hours)

    # If stop exists, the programme must not already be completely stale.
    if stop_dt is not None and stop_dt < window_start:
        return False
    return start_dt <= window_end


def convert_xmltv_timestamp(timestamp: str, timezone_name: str) -> str:
    """
    Convert standard XMLTV timestamps safely.
    Malformed upstream values are preserved instead of crashing the build.
    """
    raw = (timestamp or "").strip()
    m = re.match(r"^(\d{8}|\d{10}|\d{12}|\d{14})\s*([+-]\d{4}|Z)(.*)$", raw)
    if not m:
        return timestamp

    digits, offset, tail = m.groups()
    try:
        dt = _parse_xmltv_digits(digits)
        if offset == "Z":
            source_tz = timezone.utc
        else:
            sign = 1 if offset[0] == "+" else -1
            hours = int(offset[1:3])
            minutes = int(offset[3:5])
            if hours > 23 or minutes > 59:
                return timestamp
            source_tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
        local = dt.replace(tzinfo=source_tz).astimezone(ZoneInfo(timezone_name))
    except (ValueError, TypeError, OverflowError):
        return timestamp

    fmt = {8: "%Y%m%d", 10: "%Y%m%d%H", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}[len(digits)]
    return local.strftime(fmt) + " " + local.strftime("%z") + tail
