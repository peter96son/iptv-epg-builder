from pathlib import Path

from src.research import classify_family, build_unmatched_family_reports


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
