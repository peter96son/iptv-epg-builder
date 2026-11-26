import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_current_kbc_and_kli_channels_use_exact_runigma_ids():
    with (ROOT / "data" / "epg-bindings.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {r["playlist_name"]: r for r in csv.DictReader(f)}
    expected = {
        "KBC-В.О.В. HD": "kbc-Vov",
        "KBC-Comics HD": "kbc-Comics",
        "KBC-Elite comedy's HD": "kbc-Elite-comedys",
        "KBC-Видак HD": "kbc-Vidak",
        "KBC-ДрамаTic HD": "kbc-Drama-tic",
        "KLI Horror FHD": "kli-horror-fhd",
    }
    for name, source_id in expected.items():
        assert rows[name]["source"] == "runigma-iptv"
        assert rows[name]["source_id"] == source_id
