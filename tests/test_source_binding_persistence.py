import csv

from src import source_reselector
from src.builder import _is_evidence_quarantined_binding


def test_selected_and_quarantined_sources_survive_next_build(tmp_path):
    registry = tmp_path / "epg-bindings.csv"
    with registry.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "playlist_name", "playlist_tvg_id", "output_tvg_id", "group",
                "region", "source", "source_id", "method", "confidence",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "playlist_name": "Recovered movie",
            "source": "old-feed",
            "source_id": "old-id",
            "method": "sticky",
            "confidence": "90",
        })
        writer.writerow({
            "playlist_name": "Unresolved movie",
            "source": "known-wrong-feed",
            "source_id": "known-wrong-id",
            "method": "sticky",
            "confidence": "90",
        })

    selected_row = {
        "playlist_name": "Recovered movie",
        "playlist_tvg_id": "provider-id",
        "output_tvg_id": "movie-id",
        "group": "Кинозалы",
        "region": "",
        "source": "verified-feed",
        "source_id": "verified-id",
        "method": "current-title-consensus",
        "confidence": "100",
    }
    source_reselector._persist_source_bindings(
        [selected_row],
        {"Recovered movie": {"source": "verified-feed", "source_id": "verified-id"}},
        {"Unresolved movie": "wrong-output-id"},
        previous_by_name={
            "Unresolved movie": {
                "playlist_name": "Unresolved movie",
                "source": "known-wrong-feed",
                "source_id": "known-wrong-id",
                "method": "sticky",
                "confidence": "90",
            }
        },
        path=registry,
    )

    with registry.open(encoding="utf-8-sig", newline="") as f:
        rows = {row["playlist_name"]: row for row in csv.DictReader(f)}

    assert rows["Recovered movie"]["source"] == "verified-feed"
    assert rows["Recovered movie"]["source_id"] == "verified-id"
    assert rows["Unresolved movie"]["method"] == "evidence-quarantined"
    assert rows["Unresolved movie"]["confidence"] == "0"
    assert _is_evidence_quarantined_binding(rows["Unresolved movie"])


def test_quarantine_marker_is_case_insensitive():
    assert _is_evidence_quarantined_binding({"method": "Evidence-Quarantined"})
    assert not _is_evidence_quarantined_binding({"method": "sticky"})
