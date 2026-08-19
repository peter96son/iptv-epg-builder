
from src import metadata_enrichment as me

def test_find_by_imdb_extracts_genres_and_overview(monkeypatch):
    monkeypatch.setattr(me, "_http_json", lambda *a, **k: {
        "movie_results": [{
            "id": 1,
            "title": "Film",
            "original_title": "Film",
            "overview": "Description",
            "genre_ids": [28, 35],
            "popularity": 1,
        }],
        "tv_results": [],
    })
    row = me._tmdb_find_by_imdb_id("key", "tt1234567", "en-US", 8)
    assert row["overview"] == "Description"
    assert row["genre_ids"] == [28, 35]
    assert row["resolved_media_type"] == "movie"
