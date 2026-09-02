import xml.etree.ElementTree as ET
from src.source_catalog import _display_names, _terms_from_missing


def test_terms_cover_premiere_group_names():
    terms=_terms_from_missing([
        {"playlist_name":"Premium HD","source_id":"premium-hd"},
        {"playlist_name":"USSR HD","source_id":"USSR HD"},
    ])
    assert "premium" in terms
    assert "premiere" in terms
    assert "ussr" in terms
    assert "spg" in terms


def test_display_names_extract_all_aliases():
    elem=ET.fromstring(
        '<channel id="x"><display-name>SPG Premium</display-name>'
        '<display-name>Premium HD</display-name></channel>'
    )
    assert _display_names(elem)==["SPG Premium","Premium HD"]
