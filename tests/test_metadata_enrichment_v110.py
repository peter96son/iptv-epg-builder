from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src import metadata_enrichment as me


def _programme(
    channel: str,
    title: str,
    *,
    desc: str = "",
    year: str = "",
    category: str = "",
) -> ET.Element:
    p = ET.Element("programme", {"channel": channel})
    t = ET.SubElement(p, "title", {"lang": "ru"})
    t.text = title
    if desc:
        d = ET.SubElement(p, "desc", {"lang": "ru"})
        d.text = desc
    if year:
        d = ET.SubElement(p, "date")
        d.text = year
    if category:
        c = ET.SubElement(p, "category", {"lang": "ru"})
        c.text = category
    return p


def _tv(*programmes: ET.Element) -> ET.Element:
    tv = ET.Element("tv")
    for p in programmes:
        tv.append(p)
    return tv


def _mappings(channel: str = "movie-channel", group: str = "Кино") -> list[dict]:
    return [{"output_tvg_id": channel, "group": group}]


def _found(
    *,
    imdb_id: str = "tt2283336",
    title: str = "Люди в чёрном: Интернэшнл",
    original_title: str = "Men in Black: International",
    overview: str = "Агенты секретной организации противостоят новой инопланетной угрозе.",
    rating: str = "5.6",
    votes: int = 162195,
    genre_ids: list[int] | None = None,
    confidence: int = 98,
) -> dict:
    return {
        "status": "found",
        "imdb_id": imdb_id,
        "tmdb_id": 479455,
        "title": title,
        "original_title": original_title,
        "overview": overview,
        "genre_ids": genre_ids or [28, 35, 878],
        "query_title": title,
        "language": "ru-RU",
        "attempt": "localized+year",
        "resolver": "tmdb",
        "confidence": confidence,
        "candidate_year": "2019",
        "resolved_media_type": "movie",
        # Supplying rating data prevents unit tests from downloading IMDb datasets.
        "imdb_rating": rating,
        "imdb_votes": votes,
        "rating_source": "test-imdb-dataset",
    }


def test_add_metadata_renders_human_description_without_tt_id():
    p = _programme("c1", "х/ф Люди в черном: Интернэшнл")

    changed = me._add_metadata(
        p,
        "5.6",
        "tt2283336",
        "162195",
        overview="Агенты H и M расследуют новую угрозу.",
        genres=["Боевик", "Комедия", "Фантастика"],
    )

    assert changed
    desc = p.findtext("desc") or ""
    assert "Жанр: Боевик, Комедия, Фантастика." in desc
    assert "Агенты H и M расследуют новую угрозу." in desc
    assert "IMDb 5.6/10 · 162 195 голосов" in desc
    assert "tt2283336" not in desc

    rating = p.find("rating")
    assert rating is not None
    assert rating.get("system") == "IMDb"
    assert rating.findtext("value") == "5.6/10"

    assert p.findtext("url") == "https://www.imdb.com/title/tt2283336/"


def test_existing_provider_description_is_preserved():
    provider = "Хорошее исходное описание фильма от поставщика EPG."
    p = _programme("c1", "х/ф Тест", desc=provider)

    me._add_metadata(
        p,
        "7.1",
        "tt1234567",
        "10000",
        overview="TMDb описание не должно заменить исходное.",
        genres=["Драма"],
    )

    desc = p.findtext("desc") or ""
    assert provider in desc
    assert "TMDb описание не должно заменить исходное." not in desc
    assert "Жанр: Драма." in desc
    assert "IMDb 7.1/10 · 10 000 голосов" in desc


def test_old_generated_imdb_suffix_is_replaced_not_duplicated():
    p = _programme(
        "c1",
        "х/ф Тест",
        desc="Описание.\nIMDb 5.0/10 · 100 votes · tt1234567",
    )

    me._add_metadata(
        p,
        "5.8",
        "tt1234567",
        "2500",
        genres=["Триллер"],
    )

    desc = p.findtext("desc") or ""
    assert desc.count("IMDb") == 1
    assert "IMDb 5.8/10 · 2 500 голосов" in desc
    assert "tt1234567" not in desc


def test_genres_are_added_as_xmltv_categories_without_duplicates():
    p = _programme("c1", "х/ф Тест", category="Комедия")

    me._add_metadata(
        p,
        "6.0",
        "tt1234567",
        "10",
        genres=["Комедия", "Боевик"],
    )

    categories = [c.text for c in p.findall("category")]
    assert categories.count("Комедия") == 1
    assert "Боевик" in categories


def test_clean_search_title_removes_provider_noise():
    assert me._clean_search_title("х/ф Люди в черном 3 (16+)") == "Люди в черном 3"
    assert me._clean_search_title("т/с Квест. 5 с.") == "Квест"
    assert me._clean_search_title("х/ф Фильм (2019)") == "Фильм"


def test_series_episode_titles_share_one_canonical_identity():
    a = me._canonical_metadata_title("т/с След (Нарциссы)", "series")
    b = me._canonical_metadata_title("т/с След (Очередь)", "series")
    c = me._canonical_metadata_title("т/с След (Год спустя)", "series")

    assert a == b == c == "След"


def test_ukrainian_title_is_not_sent_to_ru_en_metadata_pipeline():
    assert me._skip_metadata_language("uk-UA", "Шпигун, який мене кинув")
    assert not me._skip_metadata_language("ru-RU", "Телохранитель жены киллера")
    assert not me._skip_metadata_language("en-US", "The Matrix")


def test_full_enrichment_adds_genre_overview_and_imdb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    tv = _tv(
        _programme(
            "movie-channel",
            "х/ф Люди в черном: Интернэшнл",
            year="2019",
        )
    )

    calls = []

    def fake_lookup(*args, **kwargs):
        calls.append((args, kwargs))
        return _found()

    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("METADATA_MAX_REQUESTS", "20000")
    monkeypatch.setattr(me, "_tmdb_lookup_imdb", fake_lookup)
    monkeypatch.setattr(me.time, "sleep", lambda *_: None)

    report = me.enrich_metadata(tv, _mappings(), tmp_path, tmp_path / "output")

    assert len(calls) == 1
    assert report["summary"]["metadata_matches"] == 1
    assert report["summary"]["programmes_enriched"] == 1
    assert report["summary"]["unique_metadata_title_lookups_used"] == 1
    assert report["summary"]["sqlite_cache"] is True

    p = tv.find("programme")
    desc = p.findtext("desc") or ""
    assert "IMDb 5.6/10 · 162 195 голосов" in desc
    assert "tt2283336" not in desc
    assert "Агенты секретной организации" in desc

    # TMDb ids 28/35/878 must be rendered through the v11 genre map.
    categories = [c.text for c in p.findall("category")]
    assert categories


def test_second_run_uses_sqlite_and_does_not_call_tmdb_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("METADATA_MAX_REQUESTS", "20000")
    monkeypatch.setattr(me.time, "sleep", lambda *_: None)

    first_tv = _tv(
        _programme("movie-channel", "х/ф Люди в черном: Интернэшнл", year="2019")
    )

    first_calls = {"count": 0}

    def first_lookup(*args, **kwargs):
        first_calls["count"] += 1
        return _found()

    monkeypatch.setattr(me, "_tmdb_lookup_imdb", first_lookup)
    first_report = me.enrich_metadata(
        first_tv, _mappings(), tmp_path, tmp_path / "output"
    )

    assert first_calls["count"] == 1
    assert first_report["summary"]["sqlite_title_entries"] >= 1

    second_tv = _tv(
        _programme("movie-channel", "х/ф Люди в черном: Интернэшнл", year="2019")
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("TMDb lookup should not run for a cached title")

    monkeypatch.setattr(me, "_tmdb_lookup_imdb", should_not_run)
    second_report = me.enrich_metadata(
        second_tv, _mappings(), tmp_path, tmp_path / "output"
    )

    assert second_report["summary"]["sqlite_title_hits"] >= 1
    assert second_report["summary"]["unique_metadata_title_lookups_used"] == 0
    assert "IMDb 5.6/10" in (second_tv.find("programme").findtext("desc") or "")


def test_many_episodes_use_one_new_title_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    programmes = [
        _programme("movie-channel", f"т/с След ({episode})")
        for episode in (
            "Нарциссы",
            "Очередь",
            "Год спустя",
            "Страшные сказки",
            "Никакого смысла",
            "Красные флаги",
        )
    ]
    tv = _tv(*programmes)

    calls = {"count": 0}

    def fake_lookup(*args, **kwargs):
        calls["count"] += 1
        result = _found(
            imdb_id="tt1360087",
            title="След",
            original_title="Sled",
            overview="Сотрудники ФЭС расследуют сложные преступления.",
            rating="3.5",
            votes=332,
            genre_ids=[80, 9648],
        )
        result["resolved_media_type"] = "series"
        return result

    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("METADATA_MAX_REQUESTS", "20000")
    monkeypatch.setattr(me, "_tmdb_lookup_imdb", fake_lookup)
    monkeypatch.setattr(me.time, "sleep", lambda *_: None)

    report = me.enrich_metadata(tv, _mappings(), tmp_path, tmp_path / "output")

    assert calls["count"] == 1
    assert report["summary"]["unique_metadata_title_lookups_used"] == 1
    assert report["summary"]["in_run_memo_hits"] == len(programmes) - 1

    for p in programmes:
        assert "IMDb 3.5/10" in (p.findtext("desc") or "")


def test_budget_counts_unique_titles_not_http_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    tv = _tv(
        _programme("movie-channel", "х/ф Первый фильм"),
        _programme("movie-channel", "х/ф Второй фильм"),
    )

    calls = {"count": 0}

    def fake_lookup(*args, **kwargs):
        calls["count"] += 1
        return _found(
            imdb_id=f"tt000000{calls['count']}",
            title=args[1],
            original_title=args[1],
            rating="6.0",
            votes=100,
            confidence=98,
        )

    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setenv("METADATA_MAX_REQUESTS", "1")
    monkeypatch.setattr(me, "_tmdb_lookup_imdb", fake_lookup)
    monkeypatch.setattr(me.time, "sleep", lambda *_: None)

    report = me.enrich_metadata(tv, _mappings(), tmp_path, tmp_path / "output")

    assert calls["count"] == 1
    assert report["summary"]["unique_metadata_title_lookups_used"] == 1
    assert report["summary"]["lookup_not_attempted"] == 1
