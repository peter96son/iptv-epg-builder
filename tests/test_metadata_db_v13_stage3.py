from pathlib import Path
from src.metadata_db import MetadataDB, SCHEMA_VERSION

def seed_matrix(db):
    db.put_title("Матрица","1999","movie","ru-RU",{
        "status":"found","imdb_id":"tt0133093","tmdb_id":603,
        "title":"Матрица","original_title":"The Matrix","overview":"Описание",
        "genre_ids":[28,878],"resolved_media_type":"movie","confidence":99,
    })
    db.teach_alias_family(["Матрица","Х/ф Матрица HD","The Matrix"],
                          "tt0133093","1999","movie",confidence=99)
    db.conn.commit()

def test_schema_v4(tmp_path: Path):
    db=MetadataDB(tmp_path/"m.sqlite3")
    try:
        assert SCHEMA_VERSION>=4
        assert db.get_stat("alias_learning_version")=="v13-stage3"
        assert "alias_conflicts" in db.counts()
    finally: db.close()

def test_quality_suffix_and_provider_prefix_resolve_locally(tmp_path: Path):
    db=MetadataDB(tmp_path/"m.sqlite3")
    try:
        seed_matrix(db)
        e=db.resolve_knowledge("Х/ф Матрица 4K","1999","movie","ru-RU")
        assert e and e["imdb_id"]=="tt0133093"
        assert e["resolver"] in {"knowledge-alias","knowledge-smart-alias"}
    finally: db.close()

def test_conflict_does_not_redirect(tmp_path: Path):
    db=MetadataDB(tmp_path/"m.sqlite3")
    try:
        db._upsert_knowledge_title(imdb_id="tt1111111",canonical_title="Один",year="2000",media_type="movie")
        db._upsert_knowledge_title(imdb_id="tt2222222",canonical_title="Два",year="2000",media_type="movie")
        assert db.learn_alias("Общее имя","tt1111111","2000","movie",confidence=99)
        assert not db.learn_alias("Общее имя","tt2222222","2000","movie",confidence=99)
        assert db.get_alias("Общее имя","2000","movie")["imdb_id"]=="tt1111111"
        assert db.counts()["alias_conflicts"]==1
    finally: db.close()

def test_repeated_alias_builds_evidence(tmp_path: Path):
    db=MetadataDB(tmp_path/"m.sqlite3")
    try:
        db._upsert_knowledge_title(imdb_id="tt3333333",canonical_title="Фильм",year="2010",media_type="movie")
        db.learn_alias("Фильм HD","tt3333333","2010","movie",confidence=98)
        db.learn_alias("Фильм HD","tt3333333","2010","movie",confidence=99)
        row=db.get_alias("Фильм HD","2010","movie")
        assert row["evidence_count"]>=2
        assert row["confidence"]==99
    finally: db.close()

def test_alias_variants_keep_sequel_number():
    variants=[x[0] for x in MetadataDB.alias_variants("Х/ф Лютый 2 4K")]
    assert "Лютый 2" in variants
    assert "Лютый" not in variants
