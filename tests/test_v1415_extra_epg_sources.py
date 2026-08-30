from src.config import load_sources


def test_v1415_independent_ru_cis_rescue_sources_are_registered():
    sources = {s["name"]: s for s in load_sources()}
    expected = {
        "teleguide-rescue": "https://teleguide.info/download/new3/xmltv.xml.gz",
        "m3u-edit-all-rescue": "https://m3u-edit.com/epg-source.php?file=ALL_SOURCES1.xml.gz",
    }
    for name, url in expected.items():
        cfg = sources[name]
        assert cfg["url"] == url
        assert cfg["rescue_source"] is True
        assert cfg["groups"] == ["Кино", "USSR", "Кинозалы", "Кино 4K"]

    for dead in ("ottepg-rescue", "kineskop-rescue", "shara-tv-rescue"):
        assert dead not in sources


def test_v1415_rescues_do_not_replace_dedicated_source_order():
    sources = load_sources()
    names = [s["name"] for s in sources]
    assert names.index("premiere-group-dedicated") < names.index("teleguide-rescue")
    assert names.index("premiere-group-dedicated") < names.index("m3u-edit-all-rescue")
