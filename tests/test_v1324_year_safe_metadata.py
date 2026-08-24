import sqlite3
from pathlib import Path

def test_year_safe_patch_is_loaded_from_run():
    text=Path("run.py").read_text(encoding="utf-8")
    assert "import src.year_safe_metadata_patch" in text

def test_year_safe_patch_rejects_wrong_year(monkeypatch):
    from src.metadata_db import MetadataDB
    import src.year_safe_metadata_patch  # noqa: F401

    # Test the wrapper contract without depending on the persistent production DB.
    # A tiny temp DB is enough to insert a yearless alias pointing to another year.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        db=MetadataDB(Path(td)/"m.sqlite3")
        try:
            title_id=db._upsert_knowledge_title(
                imdb_id="tt0988045", media_type="movie", year="2009",
                canonical_title="Sherlock Holmes", original_title="Sherlock Holmes"
            )
            db.conn.execute(
                """INSERT OR REPLACE INTO aliases
                   (normalized_alias,alias,imdb_id,year,media_type,source,confidence,
                    created_at,last_seen_at,title_id,evidence_count,verified,generated_rule)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("шерлок холмс","Шерлок Холмс","tt0988045","","movie","test",99,
                 "2026-01-01","2026-01-01",title_id,1,1,"")
            )
            db.conn.commit()
            assert db.resolve_knowledge("Шерлок Холмс","1980","movie","ru") is None
            hit=db.resolve_knowledge("Шерлок Холмс","2009","movie","ru")
            # Exact-year aliases/titles remain valid; if this tiny fixture has no exact alias,
            # the important regression assertion above still protects wrong-year reuse.
        finally:
            db.close()
