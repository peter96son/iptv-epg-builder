from __future__ import annotations

import sqlite3
from pathlib import Path

from src.metadata_db import MetadataDB, SCHEMA_VERSION


def test_v13_schema_exists_and_dual_writes(tmp_path: Path):
    db = MetadataDB(tmp_path / "metadata.sqlite3")
    try:
        assert SCHEMA_VERSION == 2
        tables = {
            r[0] for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"titles", "metadata", "people", "credits", "statistics"} <= tables

        db.put_title("Матрица", "1999", "movie", "ru-RU", {
            "status": "found",
            "imdb_id": "tt0133093",
            "tmdb_id": 603,
            "title": "Матрица",
            "original_title": "The Matrix",
            "overview": "Тестовое описание.",
            "genre_ids": [28, 878],
            "resolved_media_type": "movie",
            "resolver": "tmdb",
        })
        db.put_imdb_entity("tt0133093", {
            "rating": "8.7",
            "votes": 2100000,
            "title": "The Matrix",
            "original_title": "The Matrix",
            "year": "1999",
            "runtime_minutes": 136,
            "countries": ["US"],
            "poster_url": "https://example/poster.jpg",
        })
        db.put_alias("Х/ф Матрица HD", "tt0133093", "1999", "movie", confidence=99)

        row = db.conn.execute(
            "SELECT id, imdb_id, tmdb_id FROM titles WHERE imdb_id='tt0133093'"
        ).fetchone()
        assert row is not None
        title_id = int(row["id"])
        assert row["tmdb_id"] == 603

        md = db.conn.execute(
            "SELECT * FROM metadata WHERE title_id=?", (title_id,)
        ).fetchone()
        assert md["overview_ru"] == "Тестовое описание."
        assert md["runtime_minutes"] == 136
        assert md["imdb_rating"] == "8.7"

        alias = db.conn.execute(
            "SELECT title_id FROM aliases WHERE normalized_alias<>''"
        ).fetchone()
        assert alias["title_id"] == title_id

        assert db.get_title("Матрица", "1999", "movie", "ru-RU")["imdb_id"] == "tt0133093"
    finally:
        db.close()


def test_v12_database_migrates_in_place(tmp_path: Path):
    path = tmp_path / "metadata.sqlite3"

    # Minimal legacy schema compatible with schema v1.
    db = MetadataDB(path)
    db.put_title("Старый фильм", "2001", "movie", "ru-RU", {
        "status": "found",
        "imdb_id": "tt1234567",
        "tmdb_id": 42,
        "title": "Старый фильм",
        "original_title": "Old Film",
        "overview": "Старое описание",
        "genre_ids": [18],
        "resolved_media_type": "movie",
    })
    db.conn.execute("DELETE FROM titles")
    db.conn.execute("DELETE FROM metadata")
    db.conn.execute("UPDATE title_cache SET knowledge_title_id=NULL")
    db.conn.execute(
        "INSERT INTO schema_meta(key,value) VALUES('schema_version','1') "
        "ON CONFLICT(key) DO UPDATE SET value='1'"
    )
    db.conn.commit()
    db.close()

    # Re-opening performs idempotent in-place migration.
    migrated = MetadataDB(path)
    try:
        title = migrated.conn.execute(
            "SELECT * FROM titles WHERE imdb_id='tt1234567'"
        ).fetchone()
        assert title is not None
        md = migrated.conn.execute(
            "SELECT * FROM metadata WHERE title_id=?", (title["id"],)
        ).fetchone()
        assert md is not None
        assert md["overview_ru"] == "Старое описание"
        linked = migrated.conn.execute(
            "SELECT knowledge_title_id FROM title_cache WHERE imdb_id='tt1234567'"
        ).fetchone()
        assert linked["knowledge_title_id"] == title["id"]
        assert migrated.get_stat("knowledge_schema_version") == "2"
    finally:
        migrated.close()


def test_people_credits_and_statistics(tmp_path: Path):
    db = MetadataDB(tmp_path / "metadata.sqlite3")
    try:
        tid = db._upsert_knowledge_title(
            imdb_id="tt7654321", canonical_title="Film", year="2020", media_type="movie"
        )
        pid = db.upsert_person("Jane Doe", tmdb_id=123)
        db.put_credit(tid, pid, role="actor", character_name="Hero", billing_order=0)
        db.set_stat("coverage", "97.5")

        assert db.conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 1
        assert db.conn.execute("SELECT COUNT(*) FROM credits").fetchone()[0] == 1
        assert db.get_stat("coverage") == "97.5"
    finally:
        db.close()
