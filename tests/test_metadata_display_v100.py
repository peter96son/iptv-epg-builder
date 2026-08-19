import xml.etree.ElementTree as ET

import src.metadata_quality_patch  # noqa: F401
from src import metadata_enrichment as me


def test_v10_visible_description_genres_overview_and_rating_without_tt_id():
    p = ET.Element("programme", {"channel": "movie"})
    ET.SubElement(p, "title").text = "х/ф Телохранитель жены киллера"
    assert me._add_metadata(
        p,
        "6.1",
        "tt8385148",
        "123456",
        overview="Телохранитель снова оказывается втянут в опасную авантюру.",
        genres=["боевик", "комедия", "триллер"],
    )
    desc = p.findtext("desc") or ""
    assert desc.startswith("Жанр: боевик, комедия, триллер.")
    assert "Телохранитель снова" in desc
    assert "IMDb 6.1/10 · 123 456 голосов" in desc
    assert "tt8385148" not in desc
    assert any("tt8385148" in (u.text or "") for u in p.findall("url"))
    assert [c.text for c in p.findall("category")] == ["боевик", "комедия", "триллер"]


def test_v10_preserves_provider_description():
    p = ET.Element("programme", {"channel": "movie"})
    ET.SubElement(p, "title").text = "х/ф Пример"
    ET.SubElement(p, "desc").text = "Хорошее описание от провайдера."
    me._add_metadata(
        p, "7.2", "tt1234567", "1000",
        overview="Это описание TMDb не должно заменить исходное.",
        genres=["драма"],
    )
    desc = p.findtext("desc") or ""
    assert "Хорошее описание от провайдера." in desc
    assert "Это описание TMDb" not in desc
