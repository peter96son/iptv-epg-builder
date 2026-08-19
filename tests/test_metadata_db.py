from __future__ import annotations

from pathlib import Path

import pytest

from src.metadata_db import MetadataDB


@pytest.fixture()
def db(tmp_path: Path):
    database = MetadataDB(tmp_path / "metadata.sqlite3")
    yield database
    database.close()


def test_database_creates_expected_tables(db: MetadataDB):
    rows = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {row[0] for row in rows}

    assert "schema_meta" in names
    assert "title_cache" in names
    assert "imdb_entities" in names
    assert "aliases" in names


def test_title_roundtrip(db: MetadataDB):
    db.put_title(
        "Интерстеллар",
        "2014",
        "movie",
        "ru-RU",
        {
            "status": "found",
            "imdb_id": "tt0816692",
            "tmdb_id": 157336,
            "title": "Интерстеллар",
            "original_title": "Interstellar",
            "overview": "Описание",
            "genre_ids": [12, 18, 878],
            "query_title": "Интерстеллар",
            "resolver": "tmdb",
            "confidence": 99,
        },
    )

    row = db.get_title("Интерстеллар", "2014", "movie", "ru-RU")

    assert row is not None
    assert row["status"] == "found"
    assert row["imdb_id"] == "tt0816692"
    assert row["tmdb_id"] == 157336
    assert row["confidence"] == 99
    assert row["resolver"] == "tmdb"
    assert row["overview"] == "Описание"
    assert row["genre_ids"] == [12, 18, 878]


def test_title_key_includes_language(db: MetadataDB):
    db.put_title(
        "Arrival",
        "2016",
        "movie",
        "en-US",
        {"status": "found", "imdb_id": "tt2543164"},
    )

    assert db.get_title("Arrival", "2016", "movie", "en-US") is not None
    assert db.get_title("Arrival", "2016", "movie", "ru-RU") is None


def test_title_miss_roundtrip(db: MetadataDB):
    db.put_title(
        "Definitely Unknown Title",
        "",
        "movie",
        "en-US",
        {
            "status": "miss",
            "miss_count": 2,
            "attempts": 4,
            "resolver": "tmdb",
        },
    )

    row = db.get_title("Definitely Unknown Title", "", "movie", "en-US")

    assert row is not None
    assert row["status"] == "miss"
    assert row["miss_count"] == 2
    assert row["attempts"] == 4


def test_delete_title(db: MetadataDB):
    db.put_title(
        "Матрица",
        "1999",
        "movie",
        "ru-RU",
        {"status": "found", "imdb_id": "tt0133093"},
    )
    assert db.get_title("Матрица", "1999", "movie", "ru-RU") is not None

    db.delete_title("Матрица", "1999", "movie", "ru-RU")

    assert db.get_title("Матрица", "1999", "movie", "ru-RU") is None


def test_imdb_entity_roundtrip(db: MetadataDB):
    db.put_imdb_entity(
        "tt2283336",
        {
            "rating": "5.6",
            "votes": 162195,
            "source": "imdb-dataset",
            "title": "Men in Black: International",
            "original_title": "Men in Black: International",
            "overview": "Agents H and M face a new alien threat.",
            "genres": ["Action", "Comedy", "Science Fiction"],
            "year": "2019",
            "runtime_minutes": 115,
            "countries": ["US"],
            "poster_url": "https://image.example/poster.jpg",
            "kp_rating": "6.1",
            "kp_votes": 12345,
        },
    )

    row = db.get_imdb_entity("tt2283336")

    assert row is not None
    assert row["rating"] == "5.6"
    assert row["votes"] == "162195"
    assert row["source"] == "imdb-dataset"
    assert row["title"] == "Men in Black: International"
    assert row["genres"] == ["Action", "Comedy", "Science Fiction"]
    assert row["year"] == "2019"
    assert row["runtime_minutes"] == 115
    assert row["countries"] == ["US"]
    assert row["kp_rating"] == "6.1"
    assert row["kp_votes"] == "12345"


def test_entity_update_preserves_existing_rich_fields(db: MetadataDB):
    db.put_imdb_entity(
        "tt0133093",
        {
            "rating": "8.7",
            "votes": 100,
            "source": "first",
            "title": "The Matrix",
            "overview": "Existing overview",
            "genres": ["Action", "Science Fiction"],
            "year": "1999",
        },
    )

    db.put_imdb_entity(
        "tt0133093",
        {
            "rating": "8.7",
            "votes": 200,
            "source": "second",
            "title": "",
            "overview": "",
            "genres": [],
            "year": "",
        },
    )

    row = db.get_imdb_entity("tt0133093")

    assert row["title"] == "The Matrix"
    assert row["overview"] == "Existing overview"
    assert row["genres"] == ["Action", "Science Fiction"]
    assert row["year"] == "1999"
    assert row["votes"] == "200"
    assert row["source"] == "second"


def test_alias_roundtrip_and_yearless_fallback(db: MetadataDB):
    db.put_alias(
        "Интерстеллар",
        "tt0816692",
        "",
        "movie",
        source="learned",
        confidence=100,
    )

    row = db.get_alias("Интерстеллар", "2014", "movie")

    assert row is not None
    assert row["imdb_id"] == "tt0816692"
    assert row["confidence"] == 100
    assert row["source"] == "learned"


def test_alias_is_persistent_across_reopen(tmp_path: Path):
    path = tmp_path / "metadata.sqlite3"

    first = MetadataDB(path)
    first.put_alias(
        "Матрица",
        "tt0133093",
        "1999",
        "movie",
        source="test",
        confidence=100,
    )
    first.checkpoint()
    first.close()

    second = MetadataDB(path)
    row = second.get_alias("Матрица", "1999", "movie")
    second.close()

    assert row is not None
    assert row["imdb_id"] == "tt0133093"


def test_counts(db: MetadataDB):
    db.put_title(
        "One",
        "2001",
        "movie",
        "en-US",
        {"status": "found", "imdb_id": "tt0000001"},
    )
    db.put_imdb_entity("tt0000001", {"title": "One"})
    db.put_alias("Uno", "tt0000001", "2001", "movie")

    counts = db.counts()

    assert counts["titles"] == 1
    assert counts["imdb_entities"] == 1
    assert counts["aliases"] == 1


def test_wal_mode_is_enabled(db: MetadataDB):
    mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
    assert mode == "wal"


def test_context_manager_commits(tmp_path: Path):
    path = tmp_path / "metadata.sqlite3"

    with MetadataDB(path) as first:
        first.put_imdb_entity("tt4154796", {"rating": "8.4", "votes": 1})

    with MetadataDB(path) as second:
        row = second.get_imdb_entity("tt4154796")

    assert row is not None
    assert row["rating"] == "8.4"
