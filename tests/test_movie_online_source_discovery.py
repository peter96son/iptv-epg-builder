import csv
import json
from pathlib import Path

from src import movie_online_source_discovery as discovery


def test_missing_channel_loader_limits_scan_to_movie_groups_and_gaps(tmp_path):
    path = tmp_path / "gaps.csv"
    path.write_text(
        "group,playlist_name,provider_name,provider_tvg_id,status\n"
        "Кино, VHS HD ,VHS HD,Xvhshd,NO_MAPPING\n"
        "USSR,DITV СССР 4К,DITV СССР 4К,no_epg_cinema,NO_MAPPING\n"
        "Кино,Working Cinema,Working Cinema,Xcinema,OK\n"
        "Спорт,SPORT,SPORT,Xsport,NO_MAPPING\n",
        encoding="utf-8",
    )

    rows = discovery._missing_channels(path)

    assert [row["playlist_name"] for row in rows] == ["VHS HD", "DITV СССР 4К"]


def test_report_compares_independent_source_families_but_never_auto_binds(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    gaps = output / "movie-epg-gaps.csv"
    gaps.write_text(
        "group,playlist_name,provider_name,provider_tvg_id,status\n"
        "Кинозалы,KBC-Comics HD,KBC-Comics HD,X39800,NO_MAPPING\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(discovery, "OUTPUT", output)
    monkeypatch.setattr(discovery, "GAPS", gaps)
    monkeypatch.setattr(discovery, "REPORT", output / "report.json")
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"name": "feed-a", "url": "https://a.example/epg", "groups": ["Кинозалы"]},
        {"name": "feed-a-mirror", "url": "https://mirror.example/epg", "groups": ["Кинозалы"]},
        {"name": "feed-b", "url": "https://b.example/epg", "groups": ["Кинозалы"]},
    ])
    results = {
        "feed-a": {"source": "feed-a", "family": "shared.example", "matches": [{
            "playlist_name": "KBC-Comics HD", "group": "Кинозалы", "source_id": "kbc-comics",
            "display_names": ["KBC-Comics HD"], "programme": {"title": "Film A", "is_current": True},
        }]},
        "feed-a-mirror": {"source": "feed-a-mirror", "family": "shared.example", "matches": [{
            "playlist_name": "KBC-Comics HD", "group": "Кинозалы", "source_id": "kbc-comics-mirror",
            "display_names": ["KBC-Comics HD"], "programme": {"title": "Film A", "is_current": True},
        }]},
        "feed-b": {"source": "feed-b", "family": "b.example", "matches": [{
            "playlist_name": "KBC-Comics HD", "group": "Кинозалы", "source_id": "kbc-comics",
            "display_names": ["KBC-Comics HD"], "programme": {"title": "Film B", "is_current": True},
        }]},
    }
    monkeypatch.setattr(discovery, "_scan_source", lambda spec, channels, now, timeout: results[spec[1]["name"]])

    payload = discovery.run()

    row = payload["channels"]["KBC-Comics HD"]
    assert payload["automatic_binding"] is False
    assert row["independent_sources"] == 2
    assert row["status"] == "SOURCE_DISAGREEMENT_UNVERIFIED"
    assert len(row["outliers"]) == 1
    saved = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert saved["channels"]["KBC-Comics HD"]["status"] == row["status"]
