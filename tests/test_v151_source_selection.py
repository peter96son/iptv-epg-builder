from src.source_reselector import choose_candidate


def c(source,horizon,usable=1):
    return {"source":source,"horizon_hours":horizon,"usable":usable}


def test_later_long_source_beats_earlier_short_source():
    rows=[c("iptvx",1.5),c("openbox",30),c("gabbarit",20)]
    assert choose_candidate(rows,6)["source"]=="openbox"


def test_policy_priority_wins_when_multiple_sources_are_long_enough():
    rows=[c("dedicated",12),c("fallback",72)]
    assert choose_candidate(rows,6)["source"]=="dedicated"


def test_longest_positive_source_wins_when_all_are_short():
    rows=[c("a",1.0),c("b",4.5),c("c",2.0)]
    assert choose_candidate(rows,6)["source"]=="b"


def test_stale_or_unusable_source_never_wins():
    rows=[c("stale",-1),c("empty",40,0),c("good",2)]
    assert choose_candidate(rows,6)["source"]=="good"


def test_no_live_candidate_returns_none():
    assert choose_candidate([c("stale",-1),c("empty",50,0)],6) is None
