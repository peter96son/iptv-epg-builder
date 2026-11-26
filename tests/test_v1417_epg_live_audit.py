from src.epg_live_audit import VERIFIED
from pathlib import Path

def test_removed_bcu_target_is_not_required():
    assert "BCU СССР HD" not in VERIFIED

def test_workflow_runs_live_epg_audit():
    text=(Path(__file__).resolve().parents[1]/".github"/"workflows"/"update.yml").read_text(encoding="utf-8")
    assert "python -m src.epg_live_audit" in text
