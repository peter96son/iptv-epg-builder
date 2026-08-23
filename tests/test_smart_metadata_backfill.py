import xml.etree.ElementTree as ET

from src.metadata_backfill import _adaptive_budget, build_queue


def test_adaptive_budget_tapers_as_database_fills():
    assert _adaptive_budget(5000, {"remaining": 20000}) == 5000
    assert _adaptive_budget(5000, {"remaining": 8000}) == 3500
    assert _adaptive_budget(5000, {"remaining": 3000}) == 2500
    assert _adaptive_budget(5000, {"remaining": 1000}) == 1200
    assert _adaptive_budget(5000, {"remaining": 300}) == 500
    assert _adaptive_budget(5000, {"remaining": 50}) == 250
    assert _adaptive_budget(5000, {"remaining": 0}) == 0


def test_requested_budget_is_hard_cap():
    assert _adaptive_budget(700, {"remaining": 20000}) == 700


def test_build_queue_counts_repeated_airings(monkeypatch):
    import src.metadata_backfill as mb

    monkeypatch.setattr(mb, "_is_fiction_candidate", lambda p, g: True)
    monkeypatch.setattr(mb, "_media_type", lambda p, g: "movie")
    monkeypatch.setattr(mb, "_canonical_metadata_title", lambda t, mt: t)
    monkeypatch.setattr(mb, "_programme_language", lambda p, t: "ru")
    monkeypatch.setattr(mb, "_detect_metadata_language", lambda t, p: "ru")
    monkeypatch.setattr(mb, "_programme_year", lambda p, mt: "1975")

    tv = ET.Element("tv")
    for cid in ("a", "b", "a"):
        p = ET.SubElement(
            tv,
            "programme",
            {"channel": cid, "start": "20990101010000 +0000"},
        )
        ET.SubElement(p, "title").text = "Старший сын"

    mappings = [
        {"output_tvg_id": "a", "group": "Кино"},
        {"output_tvg_id": "b", "group": "Кино"},
    ]

    queue = build_queue(tv, mappings)
    assert len(queue) == 1
    assert queue[0]["occurrences"] == 3
    assert queue[0]["channel_count"] == 2
    assert queue[0]["future_occurrences"] == 3
