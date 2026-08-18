from src.metadata_enrichment import _best_tmdb_candidate, _title_similarity

def test_tmdb_accepts_localized_title():
    payload={"results":[{"id":286217,"title":"Марсианин","original_title":"The Martian","release_date":"2015-09-30"}]}
    result=_best_tmdb_candidate(payload,"Марсианин","2015","movie")
    assert result and result["id"]==286217 and result["_similarity"]==1.0

def test_tmdb_rejects_wrong_year():
    payload={"results":[{"id":1,"title":"Марсианин","original_title":"The Martian","release_date":"1998-01-01"}]}
    assert _best_tmdb_candidate(payload,"Марсианин","2015","movie") is None

def test_title_similarity_exact_localized():
    assert _title_similarity("Игра престолов","Игра престолов")==1.0
