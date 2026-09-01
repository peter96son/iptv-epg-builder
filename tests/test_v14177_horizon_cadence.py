from pathlib import Path
import src.horizon_guard_patch as h

def test_default_horizon_matches_build_cadence(monkeypatch):
    monkeypatch.delenv("EPG_MIN_FUTURE_HOURS",raising=False)
    assert h.DEFAULT_MIN_FUTURE_HOURS==6.0
    assert h._min_future_hours()==6.0

def test_workflow_horizon_is_six_hours():
    t=(Path(__file__).resolve().parents[1]/".github"/"workflows"/"update.yml").read_text(encoding="utf-8")
    assert 'EPG_MIN_FUTURE_HOURS: "6"' in t
    assert 'EPG_PUBLISH_MIN_FUTURE_HOURS: "6"' in t
