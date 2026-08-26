import json
from pathlib import Path

import src.title_normalization_patch  # noqa: F401
from src import metadata_enrichment as me


def test_series_strong_prefixes():
    import xml.etree.ElementTree as ET
    for title in ["т/с Морские дьяволы", "Сериал Невский", "мультсериал Три кота"]:
        p = ET.fromstring(f"<programme><title>{title}</title></programme>")
        assert me._media_type(p, "Кино") == "series"


def test_episode_suffixes_are_series_and_cleaned():
    import xml.etree.ElementTree as ET
    p = ET.fromstring("<programme><title>Мамочки. 13 с</title></programme>")
    assert me._media_type(p, "Кино") == "series"
    assert me._clean_search_title("Мамочки. 13 с") == "Мамочки"


def test_known_parenthetical_cartoon_series():
    import xml.etree.ElementTree as ET
    p = ET.fromstring("<programme><title>Три кота (Картинная галерея)</title></programme>")
    assert me._media_type(p, "Кино") == "series"
    assert me._clean_search_title("Три кота (Картинная галерея)") == "Три кота"
    assert me._clean_search_title("Простоквашино (Неудобные соседи)") == "Простоквашино"


def test_movie_year_parentheses_not_series():
    assert me._clean_search_title("Веном (2018)") == "Веном"


def test_provider_labels_removed_before_lookup():
    assert me._clean_search_title("х/ф Веном (2018)") == "Веном"
    assert me._clean_search_title("Х/Ф: Матрица") == "Матрица"
    assert me._clean_search_title("x/ф Бегущий по лезвию 2049") == "Бегущий по лезвию 2049"
    assert me._clean_search_title("т/ф Название") == "Название"
    assert me._clean_search_title("м/ф Простоквашино") == "Простоквашино"


def test_cumulative_playlist_personalizations_are_locked():
    r = json.loads((Path(__file__).resolve().parents[1]/"data"/"playlist_rules.json").read_text(encoding="utf-8"))
    g = r["group_overrides"]
    required = {
        "Fresh TV Armenia":"Музыкальные",
        "Viasat True Crime CEE":"Познавательные",
        "KBC-Animals HD":"Познавательные",
        "MM Микромир HD":"Познавательные",
        "CineMan Лесник":"Сериалы",
        "GL Невский":"Сериалы",
        "DITV Карпов":"Сериалы",
        "Velilla TV Мосгаз HD":"Сериалы",
        "НТВ Сериал Невский":"Сериалы",
        "Лавстори HD":"Сериалы",
        "Lost HD":"Сериалы",
        "Дорама HD":"Сериалы",
        "Русский Бестселлер":"Сериалы",
        "Русский Детектив":"Сериалы",
    }
    for name, group in required.items():
        assert g.get(name) == group
    for prefix in ["Cine+","Твоє Кіно","Твое Кино","PROKINO"]:
        assert prefix in r["exclude_name_prefixes"]


def test_4ever_has_two_schedule_sources():
    rows = (Path(__file__).resolve().parents[1]/"data"/"source_pins.csv").read_text(encoding="utf-8")
    assert "4ever Theater HD" in rows
    assert "iptvx-noarch,4ever-theater" in rows
    assert "openbox-tsd,4ever-theater" in rows


def test_backfill_uses_existing_normalization_policy():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/"src"/"metadata_backfill_v1325.py").read_text(encoding="utf-8")
    assert "title_normalization_patch" in text
    assert "v14_policy_patch" not in text


def test_ci_regression_year_handling():
    assert me._clean_search_title("х/ф Фильм (2019)") == "Фильм"
    assert me._clean_search_title("x/ф Бегущий по лезвию 2049") == "Бегущий по лезвию 2049"
