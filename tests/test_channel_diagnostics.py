import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from src.channel_diagnostics import build_channel_diagnostics


def _ts(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")


def test_channel_diagnostic_reports_current_and_next(tmp_path):
    now = datetime.now(timezone.utc)
    tv = ET.Element("tv")
    current = ET.SubElement(tv, "programme", {
        "channel": "Xtest",
        "start": _ts(now - timedelta(minutes=10)),
        "stop": _ts(now + timedelta(minutes=20)),
    })
    ET.SubElement(current, "title").text = "Current show"
    nxt = ET.SubElement(tv, "programme", {
        "channel": "Xtest",
        "start": _ts(now + timedelta(minutes=20)),
        "stop": _ts(now + timedelta(minutes=50)),
    })
    ET.SubElement(nxt, "title").text = "Next show"

    mappings = [{
        "playlist_name": "Test HD",
        "output_tvg_id": "Xtest",
        "source": "primary",
        "source_id": "Xtest",
        "method": "id",
        "group": "Россия",
        "region": "RU",
    }]
    payload = build_channel_diagnostics(tv, mappings, ["Test HD"], tmp_path / "diag.json")
    row = payload["channels"][0]
    assert row["status"] == "ok"
    assert row["current_programme"]["title"] == "Current show"
    assert row["upcoming_programmes"][0]["title"] == "Next show"


def test_channel_diagnostic_marks_missing_mapping(tmp_path):
    tv = ET.Element("tv")
    payload = build_channel_diagnostics(tv, [], ["Missing"], tmp_path / "diag.json")
    assert payload["channels"][0]["status"] == "not_mapped"
