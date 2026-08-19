
import xml.etree.ElementTree as ET
import src.metadata_enrichment as m


def test_imdb_page_metadata_extracts_jsonld(monkeypatch):
    html = b'<html><script type="application/ld+json">{"aggregateRating":{"ratingValue":5.7,"ratingCount":1234}}</script></html>'
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return html
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda *a, **k: Resp())
    got = m._imdb_page_metadata("tt10990862")
    assert got == {"rating":"5.7","votes":"1234"}


def test_imdb_entity_cache_prevents_repeat_network(monkeypatch):
    calls={"n":0}
    def fake(iid, timeout=12):
        calls["n"] += 1
        return {"rating":"7.6","votes":"250000"}
    monkeypatch.setattr(m, "_imdb_page_metadata", fake)
    stats=m.Counter()
    budget=m._Budget(10)
    cache={}
    a=m._resolve_imdb_entity("tt0119116", cache, budget, stats, 12)
    b=m._resolve_imdb_entity("tt0119116", cache, budget, stats, 12)
    assert a["rating"]=="7.6"
    assert a["votes"]=="250000"
    assert b==a
    assert calls["n"]==1
    assert budget.used==1


def test_direct_imdb_empty_is_cached_without_omdb(monkeypatch):
    monkeypatch.setattr(m, "_imdb_page_metadata", lambda *a, **k: {"rating":"","votes":""})
    stats=m.Counter()
    budget=m._Budget(10)
    cache={}
    got=m._resolve_imdb_entity("tt0402910", cache, budget, stats, 12)
    assert got["source"]==""
    assert got["rating"]==""
    assert got["votes"]==""
    assert stats["imdb_direct_requests"]==1

def test_add_metadata_includes_votes():
    p=ET.fromstring("<programme><title>Test</title></programme>")
    assert m._add_metadata(p,"8.1","tt1234567","1000000")
    desc=p.find("desc").text
    assert "IMDb 8.1/10" in desc
    assert "1000000 votes" in desc
    assert "tt1234567" in desc


def test_v6_structured_cache_migrates_only_positive(tmp_path):
    path=tmp_path/"metadata-v60.json"
    path.write_text(m.json.dumps({
        "schema":6,
        "version":"6.0",
        "entries":{
            "good":{"status":"found","imdb_id":"tt10990862","imdb_rating":"5.7"},
            "bad":{"status":"not_found"}
        }
    }),encoding="utf-8")
    got=m._load_cache(path)
    assert list(got)==["good"]
    assert got["good"]["imdb_id"]=="tt10990862"
