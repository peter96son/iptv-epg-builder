from types import SimpleNamespace
from src.matcher import Matcher

class DummySource:
    def __init__(self, name, ids):
        self.name = name
        self.channels = {x: object() for x in ids}
        self.names = {}

def test_hard_source_pin_blocks_earlier_wrong_source():
    aliases = [{
        "enabled":"1",
        "playlist_name":"Premium HD",
        "source":"openbox-tsd",
        "source_id":"premium-hd",
        "hard_pin":"1",
    }]
    m = Matcher(aliases)
    ch = SimpleNamespace(name="Premium HD", tvg_name="Premium HD", tvg_id="Xpremium-hd", group="Кино")
    wrong = DummySource("iptv-online-primary", {"Xpremium-hd"})
    right = DummySource("openbox-tsd", {"premium-hd"})
    assert m.match(ch, wrong, {}, allow_family=False) == (None, None, 0)
    sid, method, confidence = m.match(ch, right, {}, allow_family=False)
    assert sid == "premium-hd"
    assert method == "alias"
    assert confidence == 100

def test_non_pinned_alias_does_not_block_fallback_source():
    aliases = [{
        "enabled":"1",
        "playlist_name":"CPS USSR",
        "source":"runigma-iptv",
        "source_id":"cps-ussr",
        "hard_pin":"0",
    }]
    m = Matcher(aliases)
    ch = SimpleNamespace(name="CPS USSR", tvg_name="CPS USSR", tvg_id="cps-ussr", group="Кино")
    fallback = DummySource("openbox-tsd", {"cps-ussr"})
    sid, method, _ = m.match(ch, fallback, {}, allow_family=False)
    assert sid == "cps-ussr"
    assert method == "id"
