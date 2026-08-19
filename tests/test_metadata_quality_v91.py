from src import metadata_quality_patch as qp


def test_translit_rejects_translation_guess():
    result = {
        "title": "Clergy",
        "original_title": "Kler",
        "confidence": 94,
    }
    ok, reason = qp._translit_candidate_is_safe("х/ф Клэр", "Kler", result)
    assert not ok
    assert reason.startswith("translit_")


def test_translit_preserves_sequel_number():
    result = {
        "title": "Fury",
        "original_title": "Lyutyy",
        "confidence": 94,
    }
    ok, reason = qp._translit_candidate_is_safe("т/с Лютый 2. 1 с.", "Lyutyy", result)
    assert not ok
    assert reason == "translit_lost_significant_number"


def test_series_root_rejects_subtitle():
    ok, reason = qp._series_root_is_safe(
        "х/ф Кремень. Освобождение. 1 с.", "Кремень"
    )
    assert not ok
    assert reason == "series_root_preserved_subtitle"


def test_series_root_allows_known_location_family():
    ok, reason = qp._series_root_is_safe(
        "т/с Наш спецназ. Калининград (Эскадрон. ч. 1)", "Наш спецназ"
    )
    assert ok
    assert reason == ""


def test_legacy_found_without_confidence_is_revalidated():
    entry = qp._sanitize_cache_entry_v91({
        "status": "found",
        "imdb_id": "tt1234567",
        "resolver": "tmdb",
    })
    assert entry["status"] == "legacy_unscored"
    assert entry["cached_at"] == ""
