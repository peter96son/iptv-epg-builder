from src.utils import normalize_name, is_real_tvg_id, convert_xmltv_timestamp

def test_normalize():
    assert normalize_name("Magic Horror HD") == "magic horror"

def test_dummy_id():
    assert not is_real_tvg_id("no_epg_cinema")
    assert is_real_tvg_id("magic-horror")

def test_dst():
    assert convert_xmltv_timestamp("20260816190000 +0000", "America/Los_Angeles").endswith("-0700")
    assert convert_xmltv_timestamp("20260116190000 +0000", "America/Los_Angeles").endswith("-0800")
