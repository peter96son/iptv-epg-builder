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
