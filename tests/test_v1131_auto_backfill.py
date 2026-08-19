from pathlib import Path

def test_update_epg_owns_automatic_backfill():
    update = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    assert "group: epg-metadata" in update
    assert 'python -m src.metadata_backfill --budget "5000"' in update
    assert "python -m src.apply_metadata_to_epg" in update

def test_standalone_backfill_is_manual_only():
    backfill = Path(".github/workflows/backfill-metadata.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in backfill
    assert "schedule:" not in backfill
