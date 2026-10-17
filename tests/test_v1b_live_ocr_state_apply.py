"""Stage 1b: Update EPG applies live OCR state without harming real programmes."""
import csv
import gzip
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import src.live_ocr_current_epg as ocr

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def ts(dt):
    return dt.strftime("%Y%m%d%H%M%S +0000")


def make_env(tmp_path, programmes, uhf, mapping_rows, state=None, raw_state=None):
    root = ET.Element("tv")
    ids = {p[0] for p in programmes} | set(uhf.values())
    for cid in sorted(ids):
        ch = ET.SubElement(root, "channel", {"id": cid})
        ET.SubElement(ch, "display-name").text = cid
    for cid, start, stop, title in programmes:
        p = ET.SubElement(root, "programme", {"start": ts(start), "stop": ts(stop), "channel": cid})
        ET.SubElement(p, "title").text = title
    epg = tmp_path / "epg.xml.gz"
    with gzip.open(epg, "wb") as f:
        ET.ElementTree(root).write(f, encoding="utf-8", xml_declaration=True)
    uhf_path = tmp_path / "uhf-mapping.json"
    uhf_path.write_text(json.dumps({"channels": uhf}, ensure_ascii=False), encoding="utf-8")
    mapping = tmp_path / "mapping.csv"
    fields = ["playlist_name", "playlist_tvg_id", "output_tvg_id", "group", "region", "source", "source_id", "method", "confidence"]
    with mapping.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for name, cid in mapping_rows.items():
            w.writerow({"playlist_name": name, "output_tvg_id": cid, "source": "src", "source_id": cid})
    state_path = tmp_path / "live_ocr_epg_state.json"
    if raw_state is not None:
        state_path.write_text(raw_state, encoding="utf-8")
    elif state is not None:
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    paths = dict(epg_path=epg, uhf_path=uhf_path, mapping_path=mapping, state_path=state_path)
    return paths


def run(paths):
    return ocr.apply_state(NOW, **paths)


def programmes(paths):
    with gzip.open(paths["epg_path"], "rb") as f:
        root = ET.parse(f).getroot()
    return root, [(p.get("channel"), p.get("start"), p.get("stop"), p.findtext("title"), p.get("x-live-ocr")) for p in root.findall("programme")]


def entry(title="Фильм", start=NOW - timedelta(minutes=20), stop=NOW + timedelta(minutes=50), tvg_id="Xliveocr-old"):
    return {"title": title, "tvg_id": tvg_id, "start": start.isoformat(), "last_seen": start.isoformat(), "stop": stop.isoformat()}


def test_missing_state_keeps_epg_untouched(tmp_path):
    paths = make_env(tmp_path, [("A", NOW - timedelta(hours=1), NOW + timedelta(hours=1), "Real")], {"Chan": "A"}, {"Chan": "A"})
    before = paths["epg_path"].read_bytes()
    report = run(paths)
    assert report["applied"] == 0 and report["reason"] == "no-state"
    assert paths["epg_path"].read_bytes() == before


def test_corrupt_state_does_not_fail(tmp_path):
    paths = make_env(tmp_path, [], {"Chan": "A"}, {"Chan": "A"}, raw_state="{not json")
    before = paths["epg_path"].read_bytes()
    assert run(paths)["applied"] == 0
    assert paths["epg_path"].read_bytes() == before


def test_malformed_entries_are_ignored(tmp_path):
    state = {"Chan": {"title": "X", "start": "garbage", "stop": "garbage"}, "Other": "not a dict"}
    paths = make_env(tmp_path, [], {"Chan": "A"}, {"Chan": "A"}, state=state)
    report = run(paths)
    assert report["applied"] == 0 and report["invalid"] == 2


def test_expired_entry_is_ignored(tmp_path):
    state = {"Chan": entry(start=NOW - timedelta(hours=2), stop=NOW - timedelta(minutes=1))}
    paths = make_env(tmp_path, [], {"Chan": "A"}, {"Chan": "A"}, state=state)
    before = paths["epg_path"].read_bytes()
    report = run(paths)
    assert report["applied"] == 0 and report["expired"] == 1
    assert paths["epg_path"].read_bytes() == before


def test_real_current_programme_wins(tmp_path):
    real = ("A", NOW - timedelta(minutes=30), NOW + timedelta(minutes=30), "Real")
    paths = make_env(tmp_path, [real], {"Chan": "A"}, {"Chan": "A"}, state={"Chan": entry()})
    report = run(paths)
    assert report["applied"] == 0 and report["skipped_real_programme"] == 1
    _, progs = programmes(paths)
    assert progs == [("A", ts(real[1]), ts(real[2]), "Real", None)]


def test_empty_channel_recovered_on_current_binding_without_touching_real(tmp_path):
    past = ("A", NOW - timedelta(hours=3), NOW - timedelta(minutes=40), "Past")
    nxt = ("A", NOW + timedelta(minutes=25), NOW + timedelta(hours=2), "Next")
    # state still carries an old Xliveocr ID; the current build binds the channel to "A"
    state = {"Chan": entry(start=NOW - timedelta(hours=1), stop=NOW + timedelta(minutes=50), tvg_id="Xliveocr-stale")}
    paths = make_env(tmp_path, [past, nxt], {"Chan": "A"}, {"Chan": "A"}, state=state)
    state_before = paths["state_path"].read_bytes()
    uhf_before = paths["uhf_path"].read_bytes()
    report = run(paths)
    assert report["applied"] == 1
    root, progs = programmes(paths)
    # attached to the channel UHF actually uses, no duplicate channel created
    assert {c.get("id") for c in root.findall("channel")} == {"A"}
    ocr_progs = [p for p in progs if p[4] == "1"]
    assert len(ocr_progs) == 1
    # clipped to sit between the real programmes, never overlapping them
    assert ocr_progs[0][:4] == ("A", ts(past[2]), ts(nxt[1]), "Фильм")
    # real programmes unchanged
    assert [p for p in progs if p[4] is None] == [("A", ts(past[1]), ts(past[2]), "Past", None), ("A", ts(nxt[1]), ts(nxt[2]), "Next", None)]
    # state is read only; uhf binding unchanged
    assert paths["state_path"].read_bytes() == state_before
    assert paths["uhf_path"].read_bytes() == uhf_before


def test_unmapped_channel_gets_live_ocr_id(tmp_path):
    paths = make_env(tmp_path, [("A", NOW - timedelta(hours=1), NOW + timedelta(hours=1), "Real")], {"Other": "A"}, {"Other": "A"}, state={"New Chan": entry()})
    report = run(paths)
    assert report["applied"] == 1
    live_id = ocr._live_id("New Chan")
    root, progs = programmes(paths)
    assert live_id in {c.get("id") for c in root.findall("channel")}
    assert [p[0] for p in progs if p[4] == "1"] == [live_id]
    uhf = json.loads(paths["uhf_path"].read_text(encoding="utf-8"))["channels"]
    assert uhf == {"Other": "A", "New Chan": live_id}
    rows = list(csv.DictReader(paths["mapping_path"].open(encoding="utf-8")))
    assert {r["playlist_name"]: r["output_tvg_id"] for r in rows} == {"Other": "A", "New Chan": live_id}


def test_apply_is_idempotent(tmp_path):
    paths = make_env(tmp_path, [], {"Chan": "A"}, {"Chan": "A"}, state={"Chan": entry()})
    run(paths)
    run(paths)
    _, progs = programmes(paths)
    assert len([p for p in progs if p[4] == "1"]) == 1


def test_ocr_window_stops_at_nearest_future_programme_in_any_order(tmp_path):
    # several real programmes inside the OCR window, deliberately written out of order
    later = ("A", NOW + timedelta(minutes=40), NOW + timedelta(minutes=60), "Later")
    nearest = ("A", NOW + timedelta(minutes=10), NOW + timedelta(minutes=40), "Nearest")
    old_end = ("A", NOW - timedelta(hours=2), NOW - timedelta(minutes=50), "Old")
    recent_end = ("A", NOW - timedelta(minutes=50), NOW - timedelta(minutes=15), "Recent")
    state = {"Chan": entry(start=NOW - timedelta(hours=1), stop=NOW + timedelta(minutes=70))}
    paths = make_env(tmp_path, [later, recent_end, nearest, old_end], {"Chan": "A"}, {"Chan": "A"}, state=state)
    assert run(paths)["applied"] == 1
    _, progs = programmes(paths)
    ocr_progs = [p for p in progs if p[4] == "1"]
    assert ocr_progs[0][1:3] == (ts(recent_end[2]), ts(nearest[1]))
