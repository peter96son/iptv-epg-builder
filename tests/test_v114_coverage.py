from pathlib import Path
from src import metadata_enrichment as me

def test_title_variants_keep_sequel_and_strip_season():
    assert "Лютый 2" in me._title_variants("Лютый 2. Сезон 3")

def test_multi_candidate_recovers_type_mismatch():
    payload = {"results": [{
        "id": 1, "media_type": "tv", "name": "Квест",
        "original_name": "Квест", "first_air_date": "2015-01-01",
    }]}
    c = me._best_tmdb_multi_candidate(payload, "Квест", "2015", "movie")
    assert c and c["_resolved_type"] == "series"

def test_backfill_default_is_5000():
    wf = Path(".github/workflows/backfill-metadata.yml").read_text(encoding="utf-8")
    assert 'default: "5000"' in wf
