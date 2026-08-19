from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.metadata_db import MetadataDB, SCHEMA_VERSION
from src import metadata_enrichment as me


def seed(db: MetadataDB):
    db.put_title("Матрица", "1999", "movie", "ru-RU", {
        "status": "found",
        "imdb_id": "tt0133093",
        "tmdb_id": 603,
        "title": "Матрица",
        "original_title": "The Matrix",
        "overview": "Хакер узнаёт правду о мире.",
        "genre_ids": [28, 878],
        "resolved_media_type": "movie",
        "resolver": "tmdb",
        "confidence": 98,
    })
    db.put_imdb_entity("tt0133093", {
        "rating": "8.7",
        "votes": 2200000,
        "title": "Матрица",
        "original_title": "The Matrix",
        "year": "1999",
    })
    db.put_alias("Х/ф Матрица HD", "tt0133093", "1999", "movie", confidence=99)
    db.conn.commit()


def test_stage2_schema_and_mode(tmp_path: Path):
    db=MetadataDB(tmp_path/"metadata.sqlite3")
    try:
        assert SCHEMA_VERSION == 3
        assert db.get_stat("knowledge_resolution_mode") == "knowledge-first"
    finally:
        db.close()


def test_alias_works_with_legacy_cache_deleted(tmp_path: Path):
    db=MetadataDB(tmp_path/"metadata.sqlite3")
    try:
        seed(db)
        db.conn.execute("DELETE FROM title_cache")
        db.conn.commit()
        e=db.resolve_knowledge("Х/ф Матрица HD","1999","movie","ru-RU")
        assert e and e["imdb_id"]=="tt0133093"
        assert e["resolver"]=="knowledge-alias"
        assert "Хакер" in e["overview"]
    finally:
        db.close()


def test_exact_title_works_with_legacy_cache_deleted(tmp_path: Path):
    db=MetadataDB(tmp_path/"metadata.sqlite3")
    try:
        seed(db)
        db.conn.execute("DELETE FROM title_cache")
        db.conn.commit()
        e=db.resolve_knowledge("Матрица","1999","movie","ru-RU")
        assert e and e["tmdb_id"]==603
        assert e["resolver"]=="knowledge-title"
    finally:
        db.close()


def test_enrichment_knowledge_hit_spends_zero_tmdb(tmp_path: Path, monkeypatch):
    root=tmp_path
    output=root/"output"; output.mkdir()
    db=MetadataDB(root/".cache"/"metadata"/"metadata.sqlite3")
    try:
        seed(db)
        db.conn.execute("DELETE FROM title_cache")
        db.conn.commit()
    finally:
        db.close()

    tv=ET.Element("tv")
    p=ET.SubElement(tv,"programme",{"channel":"c1","start":"20260819120000 +0000","stop":"20260819140000 +0000"})
    ET.SubElement(p,"title",{"lang":"ru"}).text="Матрица"
    ET.SubElement(p,"category",{"lang":"ru"}).text="Фильм"

    calls={"n":0}
    def forbidden(*args,**kwargs):
        calls["n"]+=1
        raise AssertionError("TMDb called on knowledge hit")
    monkeypatch.setattr(me,"_tmdb_lookup_imdb",forbidden)
    monkeypatch.setenv("TMDB_API_KEY","test")
    monkeypatch.setenv("METADATA_MAX_TITLES","100")
    monkeypatch.setenv("METADATA_MAX_HTTP_REQUESTS","100")

    report=me.enrich_metadata(tv,[{"output_tvg_id":"c1","group":"Кино"}],root,output)
    assert calls["n"]==0
    assert report["summary"].get("knowledge_hits",0)>=1
    assert report["summary"].get("sqlite_title_hits",0)>=1
