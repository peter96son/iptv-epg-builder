import xml.etree.ElementTree as ET

from src.channel_time_offsets import load_channel_time_offsets
from src.xmltv import XMLTVSource


def _feed():
    return b'''<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="cps-ussr"><display-name>CPS USSR</display-name></channel>
  <channel id="cps-drama"><display-name>CPS Drama</display-name></channel>
  <programme channel="cps-ussr" start="20260820071100 -0700" stop="20260820085100 -0700"><title>A</title></programme>
  <programme channel="cps-drama" start="20260820071100 -0700" stop="20260820085100 -0700"><title>B</title></programme>
</tv>'''


def test_xmltv_source_shifts_only_cps_ussr(monkeypatch):
    # Keep the regression independent of today's date window.
    import src.xmltv as xmltv
    monkeypatch.setattr(xmltv, "xmltv_date_is_fresh", lambda *args, **kwargs: True)
    monkeypatch.setattr(xmltv, "xmltv_programme_is_usable", lambda *args, **kwargs: True)
    load_channel_time_offsets.cache_clear()

    source = XMLTVSource("openbox-tsd", _feed()).index()
    programmes = list(source.fresh_programmes({"cps-ussr", "cps-drama"}))
    by_channel = {p.get("channel"): p for p in programmes}

    assert by_channel["cps-ussr"].get("start") == "20260820211100 -0700"
    assert by_channel["cps-ussr"].get("stop") == "20260820225100 -0700"
    assert by_channel["cps-drama"].get("start") == "20260820071100 -0700"
    assert by_channel["cps-drama"].get("stop") == "20260820085100 -0700"
