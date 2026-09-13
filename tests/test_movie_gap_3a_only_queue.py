from pathlib import Path

def test_3b_channels_retire_from_recurring_ocr():
    src=Path("src/movie_gap_live_probe.py").read_text(encoding="utf-8")
    assert 'profile["probe_disabled_no_title"]=True' in src
    assert 'NO_ONSCREEN_TITLE_EVER_DETECTED' in src
    assert 'if profile.get("probe_disabled_no_title") is True:' in src

def test_3a_channels_remain_eligible():
    src=Path("src/movie_gap_live_probe.py").read_text(encoding="utf-8")
    assert 'profile["onscreen_title_capable"]=True' in src
    assert 'profile["probe_disabled_no_title"]=False' in src
