import xml.etree.ElementTree as ET

from src.metadata_db import MetadataDB
from src.stage7_credits import apply_xmltv_credits, get_stored_credits, store_tmdb_credits


def _seed_title(db):
    return db._upsert_knowledge_title(
        imdb_id="tt3659388", tmdb_id=286217, media_type="movie",
        year="2015", canonical_title="The Martian", original_title="The Martian",
    )


def test_store_and_read_stage7_credits(tmp_path):
    db = MetadataDB(tmp_path / "metadata.sqlite3")
    title_id = _seed_title(db)
    entry = {
        "knowledge_title_id": title_id, "imdb_id": "tt3659388",
        "tmdb_id": 286217, "resolved_media_type": "movie",
        "title": "The Martian", "year": "2015",
    }
    payload = {
        "crew": [{"id": 578, "name": "Ridley Scott", "department": "Directing", "job": "Director"}],
        "cast": [
            {"id": 1892, "name": "Matt Damon", "character": "Mark Watney", "order": 0},
            {"id": 17605, "name": "Jessica Chastain", "character": "Melissa Lewis", "order": 1},
        ],
    }
    result = store_tmdb_credits(db, entry, payload)
    assert result == {"stored": 3, "directors": 1, "actors": 2}
    credits = get_stored_credits(db, entry)
    assert credits["directors"] == ["Ridley Scott"]
    assert credits["actors"][0]["name"] == "Matt Damon"
    db.close()


def test_xmltv_credits_are_standard_and_description_untouched():
    p = ET.fromstring("<programme><title>The Martian</title><desc>Plot only.</desc></programme>")
    changed = apply_xmltv_credits(p, {
        "directors": ["Ridley Scott"],
        "actors": [{"name": "Matt Damon", "character": "Mark Watney"}],
    })
    assert changed
    assert p.findtext("desc") == "Plot only."
    assert p.findtext("credits/director") == "Ridley Scott"
    actor = p.find("credits/actor")
    assert actor.text == "Matt Damon"
    assert actor.get("role") == "Mark Watney"
