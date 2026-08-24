from pathlib import Path

def test_year_safe_patch_is_loaded_from_run():
    text=Path("run.py").read_text(encoding="utf-8")
    assert "import src.year_safe_metadata_patch" in text

def test_year_safe_patch_rejects_wrong_year():
    from src.metadata_db import MetadataDB
    import src.year_safe_metadata_patch  # noqa: F401
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        db=MetadataDB(Path(td)/"m.sqlite3")
        try:
            # aliases.imdb_id has a FK to imdb_entities.
            # Production DB always has the referenced IMDb entity first.
            db.conn.execute(
                """INSERT OR REPLACE INTO imdb_entities
                   (imdb_id,rating,votes,source,checked_at,title,original_title,
                    overview,genres_json,year,runtime_minutes,countries_json,
                    poster_url,kp_rating,kp_votes,extra_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("tt0988045","7.6",0,"test","2026-01-01",
                 "Sherlock Holmes","Sherlock Holmes","","[]","2009",None,
                 "[]","","",None,"{}")
            )

            title_id=db._upsert_knowledge_title(
                imdb_id="tt0988045",
                media_type="movie",
                year="2009",
                canonical_title="Sherlock Holmes",
                original_title="Sherlock Holmes"
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

            # Wrong-year reuse must be rejected.
            assert db.resolve_knowledge("Шерлок Холмс","1980","movie","ru") is None

            # Matching year remains valid.
            result=db.resolve_knowledge("Шерлок Холмс","2009","movie","ru")
            assert result is not None
            assert result.get("year") == "2009"
            assert result.get("imdb_id") == "tt0988045"
        finally:
            db.close()
