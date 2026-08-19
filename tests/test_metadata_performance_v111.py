from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src import metadata_enrichment as me


def test_tmdb_http_budget_is_real_http_budget(monkeypatch: pytest.MonkeyPatch):
    calls = {"search": 0, "external": 0}

    def fake_search(*args, **kwargs):
        calls["search"] += 1
        return {
            "results": [{
                "id": 123,
                "title": "Test Film",
                "original_title": "Test Film",
                "release_date": "2020-01-01",
                "overview": "Overview",
                "genre_ids": [18],
            }]
        }

    def fake_external(*args, **kwargs):
        calls["external"] += 1
        return {"imdb_id": "tt1234567"}

    monkeypatch.setattr(me, "_tmdb_search", fake_search)
    monkeypatch.setattr(me, "_tmdb_external_ids", fake_external)

    budget = me._Budget(1)
    result = me._tmdb_lookup_imdb(
        "key", "Test Film", "2020", "movie", "en-US",
        raw_title="Test Film", budget=budget, aliases={},
    )

    assert result["status"] == "budget_exhausted"
    assert calls["search"] == 1
    assert calls["external"] == 0
    assert budget.used == 1


def test_empty_plan_limit_stops_cascade(monkeypatch: pytest.MonkeyPatch):
    calls = {"search": 0}

    def empty_search(*args, **kwargs):
        calls["search"] += 1
        return {"results": []}

    monkeypatch.setattr(me, "_tmdb_search", empty_search)
    monkeypatch.setenv("TMDB_EMPTY_PLAN_LIMIT", "2")

    budget = me._Budget(20)
    result = me._tmdb_lookup_imdb(
        "key", "Лютый 2", "", "series", "ru-RU",
        raw_title="т/с Лютый 2. 1 с.", budget=budget, aliases={},
    )

    assert result["status"] == "not_found"
    assert calls["search"] == 2
    assert budget.used == 2


def test_workflow_has_single_click_metadata_pipeline():
    workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    assert 'METADATA_MAX_HTTP_REQUESTS: "0"' in workflow
    assert 'python -m src.metadata_backfill --budget "5000"' in workflow
    assert "python -m src.apply_metadata_to_epg" in workflow
    assert "actions/cache/restore@v4" in workflow
    assert "actions/cache/save@v4" in workflow
    assert "if: always()" in workflow

