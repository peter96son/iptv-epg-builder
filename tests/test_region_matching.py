from types import SimpleNamespace

from src.matcher import Matcher
from src.playlist import PlaylistChannel
from src.region import region_for_group, is_regional_sensitive, regions_compatible


def fake_source(name, channel_id, display_name):
    from src.utils import normalize_name
    return SimpleNamespace(
        name=name,
        channels={channel_id: object()},
        names={normalize_name(display_name): {channel_id}},
    )


def test_region_from_provider_group():
    assert region_for_group("Румыния") == "RO"
    assert region_for_group("Италия") == "IT"
    assert region_for_group("BE & NL") == "BE/NL"


def test_discovery_is_region_sensitive():
    assert is_regional_sensitive("Discovery Science HD RO")
    assert is_regional_sensitive("Eurosport 3 HD")
    assert not is_regional_sensitive("Кинодром")


def test_discovery_ro_rejects_wrong_country_source():
    matcher = Matcher([])
    ch = PlaylistChannel("Discovery Science HD RO", "", "Discovery Science HD RO", "Румыния")
    src = fake_source("epgshare-NL", "discovery-science.nl", "Discovery Science HD RO")
    sid, method, confidence = matcher.match(ch, src, {"regions": ["NL"]})
    assert sid is None
    assert method is None


def test_discovery_ro_accepts_ro_country_source():
    matcher = Matcher([])
    ch = PlaylistChannel("Discovery Science HD RO", "", "Discovery Science HD RO", "Румыния")
    src = fake_source("epgshare-RO", "discovery-science.ro", "Discovery Science HD RO")
    sid, method, confidence = matcher.match(ch, src, {"regions": ["RO"]})
    assert sid == "discovery-science.ro"
    assert method == "name-region"


def test_composite_be_nl_is_not_guessed_for_sensitive_brand():
    assert not regions_compatible("BE/NL", ["BE"])
    assert not regions_compatible("BE/NL", ["NL"])
    assert regions_compatible("BE/NL", ["BE/NL"])


def test_manual_alias_can_be_region_constrained():
    aliases = [{
        "enabled": "1",
        "playlist_name": "Discovery Science HD RO",
        "provider_group": "Румыния",
        "region": "RO",
        "source": "epgshare-RO",
        "source_id": "disc.ro",
    }]
    matcher = Matcher(aliases)
    ch = PlaylistChannel("Discovery Science HD RO", "", "", "Румыния")
    src = fake_source("epgshare-RO", "disc.ro", "anything")
    assert matcher.match(ch, src, {"regions": ["RO"]}) == ("disc.ro", "alias", 100)


def test_regional_family_suffix_matches_only_compatible_country():
    from types import SimpleNamespace
    matcher = Matcher([])
    src = SimpleNamespace(
        name="epgshare-RO",
        channels={"disc.ro": object()},
        names={"discovery science": {"disc.ro"}},
    )
    ch = SimpleNamespace(
        name="Discovery Science HD RO",
        tvg_name="Discovery Science HD RO",
        tvg_id="",
        group="Румыния",
    )
    assert matcher.match(ch, src, {"regions": ["RO"]}) == ("disc.ro", "family-region", 92)


def test_regional_family_suffix_rejects_wrong_country():
    from types import SimpleNamespace
    matcher = Matcher([])
    src = SimpleNamespace(
        name="epgshare-UK",
        channels={"disc.uk": object()},
        names={"discovery science": {"disc.uk"}},
    )
    ch = SimpleNamespace(
        name="Discovery Science HD RO",
        tvg_name="Discovery Science HD RO",
        tvg_id="",
        group="Румыния",
    )
    assert matcher.match(ch, src, {"regions": ["GB"]}) == (None, None, 0)


def test_regional_family_can_be_disabled_during_legacy_pass():
    matcher = Matcher([])
    src = fake_source("epgshare-RO", "disc.ro", "Discovery Science")
    ch = PlaylistChannel("Discovery Science HD RO", "", "Discovery Science HD RO", "Румыния")
    assert matcher.match(ch, src, {"regions": ["RO"]}, allow_family=False) == (None, None, 0)
    assert matcher.match_family(ch, src, {"regions": ["RO"]}) == ("disc.ro", "family-region", 92)
