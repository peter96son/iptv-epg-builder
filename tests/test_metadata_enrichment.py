import xml.etree.ElementTree as ET
from src.metadata_enrichment import _add_metadata, _existing_imdb, _media_type, enrich_metadata


def test_existing_imdb_is_normalized():
    p = ET.fromstring('<programme channel="x"><title>Test</title><desc>Рейтинг IMDb [7.6]</desc></programme>')
    rating, imdb_id = _existing_imdb(p)
    assert rating == "7.6"
    assert imdb_id == ""
    assert _add_metadata(p, rating, imdb_id)
    r = p.find('rating')
    assert r is not None and r.get('system') == 'IMDb'
    assert r.findtext('value') == '7.6/10'


def test_imdb_id_adds_url_and_description():
    p = ET.fromstring('<programme channel="x"><title>The Martian</title><desc>Sci-fi film</desc></programme>')
    assert _add_metadata(p, '8.0', 'tt3659388')
    assert 'IMDb 8.0/10' in p.findtext('desc')
    assert any('tt3659388' in (u.text or '') for u in p.findall('url'))


def test_series_detection_from_episode_num():
    p = ET.fromstring('<programme channel="x"><title>Show</title><episode-num system="xmltv_ns">0.0.</episode-num></programme>')
    assert _media_type(p, 'Россия') == 'series'


def test_enrichment_without_api_key_still_normalizes_existing(monkeypatch, tmp_path):
    monkeypatch.delenv('OMDB_API_KEY', raising=False)
    tv = ET.fromstring('<tv><programme channel="x"><title>Movie</title><desc>IMDb: 6.5 tt1234567</desc></programme></tv>')
    report = enrich_metadata(tv, [{"output_tvg_id":"x", "group":"Кино"}], tmp_path, tmp_path/'output')
    assert report['summary']['api_configured'] is False
    assert tv.find('programme/rating').findtext('value') == '6.5/10'
    assert 'tt1234567' in tv.find('programme/url').text
