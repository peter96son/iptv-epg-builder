import xml.etree.ElementTree as ET
from pathlib import Path

from src import metadata_enrichment as me
from src.metadata_db import MetadataDB, SCHEMA_VERSION


def programme(title="Матрица"):
    p=ET.Element("programme",{"channel":"c1"})
    ET.SubElement(p,"title",{"lang":"ru"}).text=title
    return p


def test_rich_description_and_xmltv_fields():
    p=programme()
    changed=me._add_metadata(
        p,"8.7","tt0133093","2200000",
        overview="Хакер узнаёт правду о мире.",
        genres=["боевик","фантастика"],
        year="1999",runtime_minutes=136,countries=["US"],
        original_title="The Matrix",display_title="Матрица",
    )
    assert changed
    desc=p.findtext("desc")
    assert "1999 · 136 мин · США" in desc
    assert "Жанр: боевик, фантастика." in desc
    assert "Оригинальное название: The Matrix." in desc
    assert "Хакер узнаёт правду" in desc
    assert "IMDb 8.7/10 · 2 200 000 голосов" in desc
    assert "tt0133093" not in desc
    assert p.findtext("date")=="1999"
    length=p.find("length")
    assert length is not None and length.text=="136" and length.get("units")=="minutes"
    assert p.findtext("country")=="США"


def test_rerender_is_idempotent():
    p=programme()
    kwargs=dict(
        overview="Описание фильма.",genres=["драма"],year="2001",
        runtime_minutes=101,countries=["France"],original_title="Original",
        display_title="Локальное",
    )
    assert me._add_metadata(p,"7.1","tt1234567","12345",**kwargs)
    first=p.findtext("desc")
    me._add_metadata(p,"7.1","tt1234567","12345",**kwargs)
    assert p.findtext("desc")==first
    assert first.count("Жанр:")==1
    assert first.count("IMDb 7.1/10")==1


def test_short_provider_stub_is_replaced_by_real_overview():
    p=programme()
    ET.SubElement(p,"desc",{"lang":"ru"}).text="Фильм"
    me._add_metadata(
        p,"","","",overview="Это полноценное длинное описание фильма, которое должно быть показано зрителю вместо технической заглушки провайдера. Здесь достаточно текста для проверки.",
        genres=["драма"],
    )
    assert "полноценное длинное описание" in p.findtext("desc")
    assert "\nФильм\n" not in ("\n"+p.findtext("desc")+"\n")


def test_imdb_genres_are_localized():
    entry={"entity_genres":["Action","Sci-Fi","Drama"]}
    assert me._genres_for_entry(entry,"movie")==["боевик","фантастика","драма"]


def test_stage5_marker(tmp_path: Path):
    db=MetadataDB(tmp_path/"m.sqlite3")
    try:
        assert SCHEMA_VERSION>=6
        assert db.get_stat("rich_epg_renderer")=="v13-stage5"
    finally:
        db.close()
