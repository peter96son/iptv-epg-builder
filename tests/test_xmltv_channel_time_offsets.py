from src.channel_time_offsets import load_channel_time_offsets
from src.xmltv import XMLTVSource


def _feed():
    return """<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="cps-ussr"><display-name>CPS USSR</display-name></channel>
  <channel id="cps-drama"><display-name>CPS Drama</display-name></channel>
  <channel id="other"><display-name>Other</display-name></channel>
  <programme channel="cps-ussr" start="20260821130700 -0700" stop="20260821143800 -0700"><title>Ne mozhet byt</title></programme>
  <programme channel="cps-drama" start="20260821100000 -0700" stop="20260821113000 -0700"><title>Drama</title></programme>
  <programme channel="other" start="20260821100000 -0700" stop="20260821113000 -0700"><title>Other</title></programme>
</tv>""".encode("utf-8")


def test_xmltv_source_shifts_entire_openbox_cps_family(monkeypatch):
    import src.xmltv as xmltv
    monkeypatch.setattr(xmltv, "xmltv_date_is_fresh", lambda *args, **kwargs: True)
    monkeypatch.setattr(xmltv, "xmltv_programme_is_usable", lambda *args, **kwargs: True)
    load_channel_time_offsets.cache_clear()

    source = XMLTVSource("openbox-tsd", _feed()).index()
    programmes = list(source.fresh_programmes({"cps-ussr", "cps-drama", "other"}))
    by_channel = {p.get("channel"): p for p in programmes}

    assert by_channel["cps-ussr"].get("start") == "20260821150700 -0700"
    assert by_channel["cps-ussr"].get("stop") == "20260821163800 -0700"
    assert by_channel["cps-drama"].get("start") == "20260821120000 -0700"
    assert by_channel["other"].get("start") == "20260821100000 -0700"
