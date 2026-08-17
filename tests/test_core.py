from src.utils import normalize_name, is_real_tvg_id, convert_xmltv_timestamp

def test_normalize():
    assert normalize_name("Magic Horror HD") == "magic horror"

def test_dummy_id():
    assert not is_real_tvg_id("no_epg_cinema")
    assert is_real_tvg_id("magic-horror")

def test_dst():
    assert convert_xmltv_timestamp("20260816190000 +0000", "America/Los_Angeles").endswith("-0700")
    assert convert_xmltv_timestamp("20260116190000 +0000", "America/Los_Angeles").endswith("-0800")


def test_timestamp_does_not_crash_on_bad_calendar_value():
    raw = "20261301120000 +0000"
    assert convert_xmltv_timestamp(raw, "America/Los_Angeles") == raw

def test_timestamp_24h_normalization():
    value = convert_xmltv_timestamp("20260816240000 +0000", "America/Los_Angeles")
    assert value.endswith("-0700")

def test_timestamp_leap_second_normalization():
    value = convert_xmltv_timestamp("20260816235960 +0000", "America/Los_Angeles")
    assert value.endswith("-0700")

from datetime import datetime, timedelta, timezone
from src.utils import xmltv_programme_is_usable


def _xmltv(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def test_programme_usable_current_or_near_future():
    now = datetime(2026, 8, 17, 19, 0, tzinfo=timezone.utc)
    assert xmltv_programme_is_usable(
        _xmltv(now - timedelta(minutes=30)),
        _xmltv(now + timedelta(minutes=30)),
        now=now,
    )
    assert xmltv_programme_is_usable(
        _xmltv(now + timedelta(hours=24)),
        _xmltv(now + timedelta(hours=25)),
        now=now,
    )


def test_programme_stale_only_is_not_usable():
    now = datetime(2026, 8, 17, 19, 0, tzinfo=timezone.utc)
    assert not xmltv_programme_is_usable(
        _xmltv(now - timedelta(days=1)),
        _xmltv(now - timedelta(hours=20)),
        now=now,
    )


def test_programme_too_far_future_is_not_usable():
    now = datetime(2026, 8, 17, 19, 0, tzinfo=timezone.utc)
    assert not xmltv_programme_is_usable(
        _xmltv(now + timedelta(days=4)),
        _xmltv(now + timedelta(days=4, hours=1)),
        now=now,
    )
