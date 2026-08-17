from src.channel_family import family_candidates


def test_family_candidates_strip_country_suffix():
    assert family_candidates("Discovery Science HD RO", "RO") == [
        "discovery science ro", "discovery science"
    ]


def test_family_candidates_do_not_strip_middle_words():
    assert family_candidates("Sky Romania Cinema", "RO") == ["sky romania cinema"]
