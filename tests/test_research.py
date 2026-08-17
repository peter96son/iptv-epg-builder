from pathlib import Path

from src.research import classify_family, build_unmatched_family_reports, russian_cis_candidate, build_russian_cis_unmatched_reports


def test_known_families():
    assert classify_family("DITV ФИЛЬМЫ") == "DITV"
    assert classify_family("VeleS Криминальный") == "VeleS"
    assert classify_family("Magic Horror") == "Magic"
    assert classify_family("Play-X Comedy") == "Play-X"
    assert classify_family("Clarity4K Cinema") == "Clarity"


def test_unknown_family_is_diagnostic_only(tmp_path: Path):
    data = [
        {"playlist_name": "BrandX Cinema", "playlist_tvg_id": "no_epg_cinema", "group": "Кинозалы"},
        {"playlist_name": "BrandX Action", "playlist_tvg_id": "", "group": "Кинозалы"},
    ]
    result = build_unmatched_family_reports(data, tmp_path)
    assert result["unmatched_channels"] == 2
    assert (tmp_path / "unmatched-families.json").exists()
    assert (tmp_path / "unmatched-families.csv").exists()
    assert (tmp_path / "unmatched-families.md").exists()
    families = {row["family"]: row["channels"] for row in result["families"]}
    assert families["Other: BrandX"] == 2



def test_russian_cis_candidate_across_topical_groups():
    ok, reason = russian_cis_candidate({"playlist_name": "Легенды Ретро FM", "group": "Музыкальные", "region": ""})
    assert ok and reason == "cyrillic-topical-group"
    ok, _ = russian_cis_candidate({"playlist_name": "Криваві Квіти HD", "group": "Кинозалы UA", "region": ""})
    assert not ok
    ok, reason = russian_cis_candidate({"playlist_name": "Телеплюс", "group": "Россия", "region": "RU"})
    assert ok and reason == "provider-region"


def test_russian_cis_report_marks_virtual_families_unsafe(tmp_path: Path):
    data = [
        {"playlist_name": "DITV ФИЛЬМЫ", "playlist_tvg_id": "no_epg_cinema", "group": "Кинозалы", "region": ""},
        {"playlist_name": "Легенды Ретро FM", "playlist_tvg_id": "", "group": "Музыкальные", "region": ""},
    ]
    result = build_russian_cis_unmatched_reports(data, tmp_path)
    assert result["candidate_channels"] == 2
    assert result["requires_manual_or_dedicated_epg"] == 1
    assert (tmp_path / "unmatched-russian-cis.md").exists()
