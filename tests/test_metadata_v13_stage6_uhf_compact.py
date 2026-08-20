import xml.etree.ElementTree as ET
from src import metadata_enrichment as me

def make_programme(title="х/ф Мышиный переполох 2025"):
    p=ET.Element("programme", {"channel":"tvboom"})
    ET.SubElement(p,"title",{"lang":"ru"}).text=title
    ET.SubElement(p,"date").text="2025"
    ET.SubElement(p,"category",{"lang":"ru"}).text="семейный"
    ET.SubElement(p,"category",{"lang":"ru"}).text="анимация"
    ET.SubElement(p,"length",{"units":"minutes"}).text="93"
    ET.SubElement(p,"country",{"lang":"ru"}).text="США"
    return p

def test_compact_title_has_movie_year_rating_one_row():
    assert me._compact_uhf_title(
        "х/ф Мышиный переполох 2025","2025","7.2"
    ) == "Мышиный переполох (2025) · IMDb 7.2"

def test_compact_output_frees_rows_for_description():
    p=make_programme()
    me._add_metadata(
        p,"7.2","tt1234567","1000",
        overview="Мышонок отправляется в большое приключение.",
        genres=["семейный","анимация","комедия"],
        year="2025",runtime_minutes=93,countries=["США"],
        display_title="х/ф Мышиный переполох 2025",
    )
    assert p.findtext("title") == "Мышиный переполох (2025) · IMDb 7.2"
    assert p.find("date") is None
    assert p.findall("category") == []
    assert p.find("length") is None
    assert p.findall("country") == []
    assert p.findtext("desc") == "Мышонок отправляется в большое приключение."
    assert "IMDb" not in p.findtext("desc")

def test_compact_title_does_not_remove_sequel_number():
    assert me._compact_uhf_title(
        "х/ф Лютый 2 2024","2024","8.1"
    ) == "Лютый 2 (2024) · IMDb 8.1"

def test_machine_rating_is_preserved():
    p=make_programme("Фильм")
    me._add_metadata(p,"8.4","tt7654321",overview="Сюжет.",year="2020")
    r=p.find("rating")
    assert r is not None and r.get("system")=="IMDb"
    assert r.findtext("value")=="8.4/10"
