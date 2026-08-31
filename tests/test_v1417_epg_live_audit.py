from src.epg_live_audit import VERIFIED
from pathlib import Path

def test_bcu_sssr_binding_is_exact():
    v=VERIFIED["BCU СССР HD"]
    assert v["source"]=="iptvx-noarch"
    assert v["source_id"]=="bcu-sssr"
    assert "bcu-sssr-hdr" in v["forbidden"]

def test_workflow_runs_live_epg_audit():
    text=(Path(__file__).resolve().parents[1]/".github"/"workflows"/"update.yml").read_text(encoding="utf-8")
    assert "python -m src.epg_live_audit" in text
