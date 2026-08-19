from pathlib import Path
from src import metadata_enrichment as me

def test_http_budget_counts_actual_requests(monkeypatch):
    calls={"n":0}
    def empty(*a,**k):
        calls["n"]+=1
        return {"results":[]}
    monkeypatch.setattr(me,"_tmdb_search",empty)
    monkeypatch.setenv("TMDB_EMPTY_PLAN_LIMIT","2")
    budget=me._Budget(2)
    result=me._tmdb_lookup_imdb("key","Лютый 2","","series","ru-RU",
                                raw_title="т/с Лютый 2. 1 с.",budget=budget,aliases={})
    assert calls["n"]==2
    assert budget.used==2
    assert result["status"] in {"not_found","budget_exhausted"}

def test_workflow_in_memory_pipeline():
    workflow=Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    builder=Path("src/builder.py").read_text(encoding="utf-8")
    assert 'BACKFILL_HTTP_BUDGET: "5000"' in workflow
    assert "python -m src.metadata_backfill" not in workflow
    assert "python -m src.apply_metadata_to_epg" not in workflow
    assert "backfill_tree(" in builder
    assert "actions/cache/restore@v4" in workflow
    assert "actions/cache/save@v4" in workflow
