import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from src.verified_metadata_fixes import apply_verified_metadata_fixes


def _write_epg(path: Path):
    root = ET.Element("tv")
    ch = ET.SubElement(root, "channel", {"id": "mm"})
    ET.SubElement(ch, "display-name").text = "MM USSR Приключения HD"

    long = ET.SubElement(root, "programme", {
        "channel": "mm",
        "start": "20260822070200 -0700",
        "stop": "20260822141700 -0700",
    })
    ET.SubElement(long, "title").text = "Два капитана (2025) · IMDb 3.9"
    ET.SubElement(long, "desc").text = "Wrong 2025 description"
    rating = ET.SubElement(long, "rating", {"system": "IMDb"})
    ET.SubElement(rating, "value").text = "3.9/10"
    ET.SubElement(long, "url").text = "https://www.imdb.com/title/tt11557780/"

    short = ET.SubElement(root, "programme", {
        "channel": "mm",
        "start": "20260823010000 -0700",
        "stop": "20260823023200 -0700",
    })
    ET.SubElement(short, "title").text = "Два капитана (2025) · IMDb 3.9"

    with gzip.open(path, "wb") as fh:
        ET.ElementTree(root).write(fh, encoding="utf-8", xml_declaration=True)


def test_verified_override_fixes_long_soviet_version_only(tmp_path: Path):
    epg = tmp_path / "epg.xml.gz"
    rules = tmp_path / "rules.json"
    _write_epg(epg)
    rules.write_text(json.dumps({
        "rules": [{
            "id": "dva",
            "enabled": True,
            "title_base": "Два капитана",
            "min_duration_minutes": 300,
            "channel_name_contains_any": ["USSR"],
            "year": "1976",
            "imdb_id": "tt0287213",
            "imdb_rating": "7.6",
            "genres": ["приключения"],
            "description": "Correct Soviet description",
        }]
    }, ensure_ascii=False), encoding="utf-8")

    result = apply_verified_metadata_fixes(epg, rules)
    assert result["changed"] == 1

    with gzip.open(epg, "rb") as fh:
        root = ET.parse(fh).getroot()

    programmes = root.findall("programme")
    assert programmes[0].findtext("title") == "Два капитана (1976) · IMDb 7.6"
    assert programmes[0].findtext("date") == "1976"
    assert programmes[0].findtext("desc") == "Correct Soviet description"
    assert programmes[0].find("rating/value").text == "7.6/10"
    assert "tt0287213" in programmes[0].findtext("url")
    assert programmes[1].findtext("title") == "Два капитана (2025) · IMDb 3.9"
