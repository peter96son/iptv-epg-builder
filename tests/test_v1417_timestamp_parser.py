from src.epg_live_audit import _ts
def test_timestamp_variants():
    for x in ("20260831155700 -0700","202608311557 -0700","202608311557000 -0700","20260831155700123 +0300","20260831225700 Z"):
        assert _ts(x) is not None
def test_bad_timestamp_is_skipped():
    assert _ts("garbage") is None
    assert _ts("20269999999999 +0000") is None
