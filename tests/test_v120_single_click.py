from pathlib import Path

def test_update_order_is_build_backfill_finalize_commit():
    wf = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    assert wf.index("run: python run.py") < wf.index("python -m src.metadata_backfill")
    assert wf.index("python -m src.metadata_backfill") < wf.index("python -m src.apply_metadata_to_epg")
    assert wf.index("python -m src.apply_metadata_to_epg") < wf.index("Commit updated EPG output")

def test_initial_build_uses_sqlite_only():
    wf = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    section = wf.split("- name: Build EPG", 1)[1].split("- name: Backfill metadata", 1)[0]
    assert 'METADATA_MAX_HTTP_REQUESTS: "0"' in section

def test_finalize_is_local_only():
    code = Path("src/apply_metadata_to_epg.py").read_text(encoding="utf-8")
    assert 'METADATA_MAX_HTTP_REQUESTS"] = "0"' in code
    assert "_write_epg_atomic" in code
