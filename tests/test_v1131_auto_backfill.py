from pathlib import Path


def test_update_owns_backfill_in_builder():
    update = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    builder = Path("src/builder.py").read_text(encoding="utf-8")
    assert "group: epg-metadata" in update
    assert 'BACKFILL_HTTP_BUDGET: "5000"' in update
    assert "backfill_tree(" in builder


def test_standalone_backfill_supports_manual_and_nightly_smart_maintenance():
    wf = Path(".github/workflows/backfill-metadata.yml").read_text(encoding="utf-8")

    # Manual maintenance remains available.
    assert "workflow_dispatch:" in wf

    # v13.19: the standalone maintenance job now also runs nightly.
    assert "schedule:" in wf
    assert 'cron: "20 11 * * *"' in wf

    # Update EPG and standalone maintenance must never mutate metadata concurrently.
    assert "group: epg-metadata" in wf
    assert "cancel-in-progress: false" in wf

    # Durable SQLite must be restored before work and saved afterwards.
    assert "python -m src.metadata_snapshot restore" in wf
    assert "python -m src.metadata_snapshot save" in wf

    # The persistent snapshot and growth reports must be committed.
    assert "data/metadata.sqlite3.gz" in wf
    assert "output/metadata-backfill.json" in wf
    assert "output/metadata-growth-history.json" in wf

    # Nightly mode uses the smart backfill implementation rather than a blind loop.
    assert "python -m src.metadata_backfill" in wf
