from datetime import datetime, timezone

from src.movie_epg_recovery import _summarize_source_votes


def _vote(source, family, title, similarity=1.0, priority=0):
    return {
        "playlist_name": "Cinema One",
        "source": source,
        "source_id": "cinema-one",
        "family": family,
        "priority": priority,
        "title": title,
        "title_norm": title.casefold(),
        "similarity": similarity,
    }


def test_three_independent_sources_outvote_one_different_schedule():
    observations = [{
        "playlist_name": "Cinema One",
        "title": "The Same Movie",
        "when": datetime(2026, 11, 25, 10, tzinfo=timezone.utc),
    }]
    votes = [
        _vote("feed-a", "a.example", "The Same Movie"),
        _vote("feed-b", "b.example", "The Same Movie"),
        _vote("feed-c", "c.example", "The Same Movie"),
        _vote("feed-d", "d.example", "A Different Movie", 0.2),
    ]

    channel = _summarize_source_votes(observations, votes)["channels"]["Cinema One"]

    assert channel["status"] == "CONSENSUS"
    assert channel["independent_sources"] == 4
    assert channel["consensus_votes"] == 3
    assert [item["source"] for item in channel["outliers"]] == ["feed-d"]


def test_mirrors_count_as_one_source_and_tie_does_not_create_consensus():
    observations = [{
        "playlist_name": "Cinema One",
        "title": "The Same Movie",
        "when": datetime(2026, 11, 25, 10, tzinfo=timezone.utc),
    }]
    votes = [
        _vote("mirror-a", "same.example", "The Same Movie", priority=0),
        _vote("mirror-b", "same.example", "A Different Movie", priority=1),
        _vote("other-feed", "other.example", "A Different Movie"),
    ]

    channel = _summarize_source_votes(observations, votes)["channels"]["Cinema One"]

    assert channel["status"] == "NO_SOURCE_CONSENSUS"
    assert channel["independent_sources"] == 2
