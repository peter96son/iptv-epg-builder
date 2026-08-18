from datetime import datetime
from zoneinfo import ZoneInfo

from src.ditv_fallback import is_ditv_channel, ditv_id, build_ditv_fallback
from src.utils import xmltv_programme_is_usable


def test_ditv_detection():
    assert is_ditv_channel("DITV Карпов")
    assert is_ditv_channel("ditv Game of Thrones")
    assert not is_ditv_channel("Discovery Science")


def test_ditv_id_is_stable_and_distinct():
    assert ditv_id("DITV Карпов") == ditv_id("DITV   Карпов")
    assert ditv_id("DITV Карпов") != ditv_id("DITV Глухарь")


def test_fallback_has_current_usable_programme():
    now = datetime(2026, 8, 17, 15, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    cid, ch, programmes = build_ditv_fallback("DITV Карпов", "America/Los_Angeles", now=now)
    assert ch.get("id") == cid
    assert len(programmes) >= 40
    assert any(xmltv_programme_is_usable(p.get("start"), p.get("stop"), now=now) for p in programmes)
    assert all("Карпов" in (p.findtext("title") or "") for p in programmes)
