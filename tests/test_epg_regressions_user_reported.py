from src.source_evidence import _similar
from src.movie_gap_live_probe import _variant_plan

def test_hf_prefix_does_not_break_title_match():
    assert _similar("х/ф Визит к Минотавру 3", "Визит к Минотавру 3") >= 0.99

def test_ditv_plan_contains_left_bottom_zone():
    plan = _variant_plan("DITV КОМЕДИИ СССР")
    assert "left_bottom_tight" in plan
    assert "left_bottom" in plan
