from src.source_evidence import _distinct_matched_titles
from src.source_reselector import _existing_donor_contradicted


def test_same_title_twice_is_not_two_independent_proofs():
    matches = [
        {"observed_title": "Спутник (2020)", "matched": True},
        {"observed_title": "Спутник", "matched": True},
    ]
    assert _distinct_matched_titles(matches) == 1


def test_two_different_titles_are_independent_proofs():
    matches = [
        {"observed_title": "Спутник (2020)", "matched": True},
        {"observed_title": "Солярис", "matched": True},
    ]
    assert _distinct_matched_titles(matches) == 2


def test_pending_evidence_does_not_contradict_existing_donor():
    existing = {"source": "tvteam", "source_id": "ch2802", "output_tvg_id": "veles-our-cinema"}
    candidates = [
        {"source": "tvteam", "source_id": "ch2802", "_evidence_negative": 0},
    ]
    assert _existing_donor_contradicted(existing, candidates) is False


def test_explicit_negative_evidence_contradicts_existing_donor():
    existing = {"source": "tvteam", "source_id": "ch2802", "output_tvg_id": "veles-our-cinema"}
    candidates = [
        {"source": "tvteam", "source_id": "ch2802", "_evidence_negative": 1},
    ]
    assert _existing_donor_contradicted(existing, candidates) is True


def test_unrelated_bad_candidate_cannot_quarantine_existing_donor():
    existing = {"source": "tvteam", "source_id": "ch2802", "output_tvg_id": "veles-our-cinema"}
    candidates = [
        {"source": "other", "source_id": "bad", "_evidence_negative": 5},
    ]
    assert _existing_donor_contradicted(existing, candidates) is False
