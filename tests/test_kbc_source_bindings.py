import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_current_kbc_channels_use_openbox_ids():
    with (ROOT / "data" / "epg-bindings.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {r["playlist_name"]: r for r in csv.DictReader(f)}
    expected = {
        "KBC-Comics HD": "kbc-comics",
        "KBC-Elite comedy's HD": "kbc-elite-comedys",
        "KBC-ДрамаTic HD": "kbc-drama-tic",
    }
    for name, source_id in expected.items():
        assert rows[name]["source"] == "openbox-tsd"
        assert rows[name]["source_id"] == source_id
