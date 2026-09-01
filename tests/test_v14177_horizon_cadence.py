from pathlib import Path
import src.horizon_guard_patch as h

def test_v15_horizon_is_observer_not_filter(monkeypatch):
    monkeypatch.delenv("EPG_MIN_FUTURE_HOURS",raising=False)
    assert h.DEFAULT_MIN_FUTURE_HOURS == 6.0

def test_v15_update_runs_every_three_hours():
    t=(Path(__file__).resolve().parents[1]/".github"/"workflows"/"update.yml").read_text(encoding="utf-8")
    assert 'cron: "17 */3 * * *"' in t
    assert 'EPG_MIN_FUTURE_HOURS: "6"' in t
    assert 'EPG_PUBLISH_MIN_FUTURE_HOURS: "6"' in t
