import json
import xml.etree.ElementTree as ET
from pathlib import Path

import src.metadata_enrichment as m


def test_ukrainian_overrides_bad_ru_provider_tag():
    assert m._detect_metadata_language("П'ятий елемент", "ru-RU") == "uk"
    assert m._detect_metadata_language("Миротворець", "ru-RU") == "uk"
    assert m._skip_metadata_language("ru-RU", "Зоряна брама")


def test_ru_and_en_are_allowed():
    assert m._detect_metadata_language("Купель дьявола", "ru-RU") == "ru"
    assert m._detect_metadata_language("The Martian", "en-US") == "en"
    assert not m._skip_metadata_language("ru-RU", "Купель дьявола")


def test_transliteration_variant_exists():
    variants = m._title_variants("Купель дьявола")
    assert any(v.lower() == "kupel dyavola" for v in variants)


def test_multipart_movie_is_reclassified_and_collapsed():
    raw = "х/ф Отравленная жизнь. 4 с."
    assert m._effective_metadata_type(raw, "movie") == "series"
    assert m._canonical_metadata_title(raw, "series") == "Отравленная жизнь"


def test_series_title_year_is_not_used_as_production_year():
    p = ET.fromstring('<programme><title>Десантура. Никто, кроме нас (1995 год)</title></programme>')
    assert m._programme_year(p, "series") == ""
    assert m._programme_year(p, "movie") == "1995"


def test_legacy_cache_migrates_only_found(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "ok": {"status":"found", "imdb_id":"tt10990862"},
        "bad": {"status":"not_found"},
    }), encoding="utf-8")
    loaded = m._load_cache(path)
    assert "ok" in loaded
    assert "bad" not in loaded


def test_no_imdb_candidate_does_not_stop_later_match(monkeypatch):
    calls = []
    def fake_search(api_key, title, year, media_type, language="en-US", timeout=12):
        calls.append((title, media_type, language))
        if media_type == "series":
            return {"results":[{"id":2,"name":title,"original_name":title,"first_air_date":"2018-01-01"}]}
        return {"results":[{"id":1,"title":title,"original_title":title,"release_date":"2018-01-01"}]}
    def fake_ext(api_key, tmdb_id, media_type, timeout=12):
        return {"imdb_id": "" if tmdb_id == 1 else "tt10990862"}
    monkeypatch.setattr(m, "_tmdb_search", fake_search)
    monkeypatch.setattr(m, "_tmdb_external_ids", fake_ext)
    budget = m._Budget(20)
    r = m._tmdb_lookup_imdb("k", "Купель дьявола", "", "movie", "ru-RU", raw_title="Купель дьявола. 1 с.", budget=budget)
    assert r["status"] == "found"
    assert r["imdb_id"] == "tt10990862"


def test_in_run_memo_uses_one_resolver_for_many_episodes(monkeypatch, tmp_path):
    monkeypatch.setenv("TMDB_API_KEY", "x")
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    monkeypatch.setenv("METADATA_MAX_REQUESTS", "50")
    calls = {"n":0}
    def fake_lookup(*args, **kwargs):
        calls["n"] += 1
        return {"status":"found","imdb_id":"tt10990862","imdb_rating":"5.7","query_title":"Купель дьявола","language":"ru-RU","attempt":"test","title":"Купель дьявола"}
    monkeypatch.setattr(m, "_tmdb_lookup_imdb", fake_lookup)
    xml = '<tv>' + ''.join(f'<programme channel="x"><title lang="ru">х/ф Купель дьявола. {i} с.</title></programme>' for i in range(1, 121)) + '</tv>'
    tv = ET.fromstring(xml)
    report = m.enrich_metadata(tv, [{"output_tvg_id":"x","group":"Кино"}], tmp_path, tmp_path/"out")
    assert calls["n"] == 1
    assert report["summary"]["in_run_memo_hits"] == 119
