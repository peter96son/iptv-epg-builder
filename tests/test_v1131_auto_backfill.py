from pathlib import Path
def test_update_owns_backfill_in_builder():
    update=Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    builder=Path("src/builder.py").read_text(encoding="utf-8")
    assert "group: epg-metadata" in update
    assert 'BACKFILL_HTTP_BUDGET: "5000"' in update
    assert "backfill_tree(" in builder
def test_standalone_backfill_manual_only():
    wf=Path(".github/workflows/backfill-metadata.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in wf
    assert "schedule:" not in wf
