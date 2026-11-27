import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from src import movie_online_source_discovery as discovery


def test_missing_channel_loader_limits_scan_to_movie_groups_and_gaps(monkeypatch, tmp_path):
    path = tmp_path / "gaps.csv"
    path.write_text(
        "group,playlist_name,provider_name,provider_tvg_id,status\n"
        "Кино, VHS HD ,VHS HD,Xvhshd,NO_MAPPING\n"
        "USSR,DITV СССР 4К,DITV СССР 4К,no_epg_cinema,NO_MAPPING\n"
        "Кино,Working Cinema,Working Cinema,Xcinema,OK\n"
        "Спорт,SPORT,SPORT,Xsport,NO_MAPPING\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(discovery, "TARGETS", tmp_path / "no-targets.csv")

    rows = discovery._missing_channels(path)

    assert [row["playlist_name"] for row in rows] == ["VHS HD", "DITV СССР 4К"]


def test_report_checks_missing_channel_coverage_and_seven_day_schedule(monkeypatch, tmp_path):
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
    monkeypatch.setattr(discovery, "TARGETS", tmp_path / "no-targets.csv")
    monkeypatch.setattr(discovery, "REPORT", output / "report.json")
    monkeypatch.setattr(discovery, "CANDIDATES", tmp_path / "candidates.json")
    discovery.CANDIDATES.write_text(json.dumps([
        {"name": "candidate-feed", "url": "https://candidate.example/epg"},
    ]), encoding="utf-8")
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"name": "feed-a", "url": "https://a.example/epg", "groups": ["Кинозалы"]},
    ])
    monkeypatch.setattr(discovery, "_scan_source", lambda spec, channels, now, timeout: {
        "source": spec[1]["name"], "url": spec[1]["url"], "kind": spec[1]["kind"],
        "family": "candidate.example" if spec[1]["name"] == "candidate-feed" else "a.example",
        "matches": [{
            "playlist_name": "KBC-Comics HD", "group": "Кинозалы", "source_id": "kbc-comics",
            "display_names": ["KBC-Comics HD"], "programmes_7d": 3 if spec[1]["name"] == "feed-a" else 0,
            "current_programmes": ([{"title": "Known Film", "start": "2026-11-26T09:00:00+00:00", "stop": "2026-11-26T11:00:00+00:00"}]
                                    if spec[1]["name"] == "feed-a" else []),
        }],
    })

    payload = discovery.run()

    row = payload["channels_without_provider_schedule"][0]
    assert payload["automatic_binding"] is False
    assert payload["programme_title_comparison"] is True
    assert payload["sources_scanned"] == 2
    assert [source["source"] for source in row["sources_with_channel"]] == ["candidate-feed", "feed-a"]
    assert [source["source"] for source in row["sources_with_7d_schedule"]] == ["feed-a"]
    assert row["current_schedule_consensus"]["status"] == "INSUFFICIENT_INDEPENDENT_SOURCES"
    assert row["current_schedule_consensus"]["title"] == "Known Film"
    saved = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert saved["channels_without_provider_schedule"][0]["playlist_name"] == "KBC-Comics HD"


def test_source_inventory_deduplicates_exact_feed_urls(monkeypatch, tmp_path):
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps([
        {"name": "same-feed", "url": "https://configured.example/epg/"},
        {"name": "new-feed", "url": "https://new.example/epg"},
    ]), encoding="utf-8")
    monkeypatch.setattr(discovery, "CANDIDATES", candidates)
    monkeypatch.setattr(discovery, "TARGETS", tmp_path / "no-targets.csv")
    monkeypatch.setattr(discovery, "load_sources", lambda: [
        {"name": "configured", "url": "https://configured.example/epg", "groups": ["USSR"]},
    ])

    rows = discovery._source_inventory()

    assert [(row["name"], row["kind"]) for row in rows] == [
        ("configured", "configured"), ("new-feed", "candidate"),
    ]


def test_feed_scan_counts_only_upcoming_programmes_for_exact_missing_channel(monkeypatch):
    payload = b"""<tv>
      <channel id="kbc-comics"><display-name>KBC-Comics</display-name></channel>
      <channel id="other"><display-name>Other Channel</display-name></channel>
      <programme start="20261125120000 +0000" stop="20261125130000 +0000" channel="kbc-comics"><title>Upcoming Film</title></programme>
      <programme start="20261125100000 +0000" stop="20261125110000 +0000" channel="kbc-comics"><title>Current Film</title></programme>
      <programme start="20261205120000 +0000" stop="20261205130000 +0000" channel="kbc-comics"><title>Outside seven days</title></programme>
      <programme start="20261125120000 +0000" stop="20261125130000 +0000" channel="other"><title>Other schedule</title></programme>
    </tv>"""
    monkeypatch.setattr(discovery, "fetch_bytes", lambda *args, **kwargs: payload)
    target = [{
        "playlist_name": "KBC-Comics HD", "provider_name": "KBC-Comics HD",
        "group": "Кинозалы", "provider_tvg_id": "no_epg_cinema",
    }]
    source = {"name": "test-feed", "url": "https://feed.example/epg", "kind": "candidate"}

    result = discovery._scan_source((0, source), target, datetime(2026, 11, 25, 10, tzinfo=timezone.utc), 5)

    assert result["matches"][0]["playlist_name"] == "KBC-Comics HD"
    assert result["matches"][0]["programmes_7d"] == 2
    assert result["matches"][0]["current_programmes"][0]["title"] == "Current Film"


def test_current_title_consensus_counts_hosts_and_reports_outlier_and_mirror_conflict():
    channel = {"sources_with_channel": [
        {"source": "a", "family": "one.example", "source_id": "a1", "current_programmes": [{"title": "12 стульев", "start": "s", "stop": "e"}]},
        {"source": "a mirror", "family": "one.example", "source_id": "a2", "current_programmes": [{"title": "Чужая родня", "start": "s", "stop": "e"}]},
        {"source": "b", "family": "two.example", "source_id": "b1", "current_programmes": [{"title": "12 стульев", "start": "s", "stop": "e"}]},
        {"source": "c", "family": "three.example", "source_id": "c1", "current_programmes": [{"title": "12 стульев", "start": "s", "stop": "e"}]},
        {"source": "d", "family": "four.example", "source_id": "d1", "current_programmes": [{"title": "Королева бензоколонки", "start": "s", "stop": "e"}]},
    ]}

    result = discovery._summarize_current_schedules(channel)

    assert result["status"] == "SOURCE_CONSENSUS_UNVERIFIED"
    assert result["title"] == "12 стульев"
    assert result["independent_sources"] == 3
    assert result["consensus_votes"] == 2
    assert len(result["outliers"]) == 1
    assert result["same_family_conflicts"] == [{"family": "one.example", "titles": ["12 стульев", "чужая родня"]}]
