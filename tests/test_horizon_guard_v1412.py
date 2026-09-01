from __future__ import annotations
import gzip, json
from datetime import datetime, timedelta, timezone
import src.horizon_guard_patch  # noqa: F401
from src.xmltv import XMLTVSource
from src.epg_horizon_audit import audit

def _xml(stop_hours):
    now=datetime.now(timezone.utc)
    start=(now-timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0000")
    stop=(now+timedelta(hours=stop_hours)).strftime("%Y%m%d%H%M%S +0000")
    return f'<tv><channel id="x"><display-name>X</display-name></channel><programme channel="x" start="{start}" stop="{stop}"><title>T</title></programme></tv>'.encode()

def test_short_but_current_source_is_kept(monkeypatch):
    monkeypatch.setenv("EPG_MIN_FUTURE_HOURS","12")
    s=XMLTVSource("short",_xml(4)).index()
    assert "x" in s.channels
    assert s.horizon_hours_by_id["x"] < 12
    assert "x" in s.short_horizon_ids

def test_long_source_is_kept(monkeypatch):
    monkeypatch.setenv("EPG_MIN_FUTURE_HOURS","12")
    s=XMLTVSource("long",_xml(48)).index()
    assert "x" in s.channels
    assert s.horizon_hours_by_id["x"] > 47

def test_final_audit_warns_but_does_not_mark_expiring_as_fatal(tmp_path):
    now=datetime(2026,8,27,18,0,tzinfo=timezone.utc)
    start=(now-timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0000")
    stop=(now+timedelta(hours=2)).strftime("%Y%m%d%H%M%S +0000")
    epg=tmp_path/"epg.xml.gz"
    with gzip.open(epg,"wb") as f:
        f.write(f'<tv><programme channel="x" start="{start}" stop="{stop}"><title>T</title></programme></tv>'.encode())
    mapping=tmp_path/"map.json"
    mapping.write_text(json.dumps({"channels":{"X":"x"}}),encoding="utf-8")
    summary, rows=audit(epg,mapping,now=now,min_hours=6)
    assert summary["bad_unique_ids"] == 0
    assert summary["warning_unique_ids"] == 1
    assert rows[0]["status"] == "EXPIRING_SOON"
