from __future__ import annotations

import gzip
from collections import Counter
from pathlib import Path

from src import metadata_enrichment as me
from src.metadata_db import MetadataDB, SCHEMA_VERSION


def write_gz(path: Path, text: str):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)


def test_local_imdb_db_contains_basics_and_ratings(tmp_path: Path):
    basics=tmp_path/"basics.gz"
    ratings=tmp_path/"ratings.gz"
    db_path=tmp_path/"imdb.sqlite3"
    write_gz(
        basics,
        "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n"
        "tt0133093\tmovie\tThe Matrix\tThe Matrix\t0\t1999\t\\N\t136\tAction,Sci-Fi\n"
    )
    write_gz(
        ratings,
        "tconst\taverageRating\tnumVotes\n"
        "tt0133093\t8.7\t2200000\n"
    )
    me._build_imdb_local_db(basics,ratings,db_path)
    conn=me._open_imdb_local_db(db_path)
    try:
        row=me._lookup_imdb_local(conn,"tt0133093")
        assert row["title"]=="The Matrix"
        assert row["original_title"]=="The Matrix"
        assert row["year"]=="1999"
        assert row["runtime_minutes"]==136
        assert row["genres"]==["Action","Sci-Fi"]
        assert row["rating"]=="8.7"
        assert row["votes"]=="2200000"
    finally:
        conn.close()


def test_local_lookup_is_zero_http_per_title(tmp_path: Path):
    basics=tmp_path/"basics.gz"
    ratings=tmp_path/"ratings.gz"
    db_path=tmp_path/"imdb.sqlite3"
    write_gz(
        basics,
        "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n"
        "tt0133093\tmovie\tThe Matrix\tThe Matrix\t0\t1999\t\\N\t136\tAction,Sci-Fi\n"
    )
    write_gz(
        ratings,
        "tconst\taverageRating\tnumVotes\n"
        "tt0133093\t8.7\t2200000\n"
    )
    me._build_imdb_local_db(basics,ratings,db_path)
    conn=me._open_imdb_local_db(db_path)
    try:
        row=me._lookup_imdb_local(conn,"tt0133093")
        assert row["source"]=="imdb-official-local"
        assert me._imdb_type_to_media_type(row["title_type"])=="movie"
    finally:
        conn.close()


def test_stage4_schema_marker(tmp_path: Path):
    db=MetadataDB(tmp_path/"metadata.sqlite3")
    try:
        assert SCHEMA_VERSION>=5
        assert db.get_stat("imdb_local_layer")=="official-basics+ratings"
    finally:
        db.close()
