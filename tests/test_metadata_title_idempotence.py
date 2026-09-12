import xml.etree.ElementTree as ET
from src.metadata_enrichment import _add_metadata

def test_repairs_repeated_metadata_suffix_and_stays_idempotent():
    p=ET.fromstring('<programme><title>Своя в доску (2026) · IMDb 4.7 (2026) · IMDb 4.7 (2026) · IMDb 4.7</title></programme>')
    _add_metadata(p, '4.7', 'tt1234567', year='2026', display_title=p.findtext('title'))
    assert p.findtext('title') == 'Своя в доску (2026) · IMDb 4.7'
    _add_metadata(p, '4.7', 'tt1234567', year='2026', display_title=p.findtext('title'))
    assert p.findtext('title') == 'Своя в доску (2026) · IMDb 4.7'
