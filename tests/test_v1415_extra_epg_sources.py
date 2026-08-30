from src.config import load_sources


def test_v1415_independent_ru_cis_rescue_sources_are_registered():
    sources = {s["name"]: s for s in load_sources()}
    expected = {
        "teleguide-rescue": "https://teleguide.info/download/new3/xmltv.xml.gz",
        "ottepg-rescue": "https://ottepg.ru/ottepg.xml.gz",
        "kineskop-rescue": "http://st.kineskop.tv/epg.xml.gz",
        "shara-tv-rescue": "http://stb.shara-tv.org/epg/epgtv.xml.gz",
    }
    for name, url in expected.items():
        cfg = sources[name]
        assert cfg["url"] == url
        assert cfg["enabled"] is True
        assert cfg["rescue_source"] is True
        assert cfg["groups"] == ["Кино", "USSR", "Кинозалы", "Кино 4K"]
        assert cfg["stale_if_error_seconds"] == 172800


def test_v1415_rescues_do_not_replace_dedicated_source_order():
    sources = load_sources()
    names = [s["name"] for s in sources]
    # Dedicated Premiere must stay ahead of every new generic rescue.
    assert names.index("premiere-group-dedicated") < names.index("teleguide-rescue")
    assert names.index("premiere-group-dedicated") < names.index("ottepg-rescue")
