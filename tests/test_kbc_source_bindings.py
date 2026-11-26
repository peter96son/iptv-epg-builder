import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kbc_bindings_use_source_specific_ids_and_kli_horror_uses_runigma():
    with (ROOT / "data" / "epg-bindings.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = {r["playlist_name"]: r for r in csv.DictReader(f)}
    expected = {
        "KBC-В.О.В. HD": ("iptvx-noarch", "kbc-vov"),
        "KBC-Comics HD": ("iptvx-noarch", "kbc-comics"),
        "KBC-Elite comedy's HD": ("iptvx-noarch", "kbc-elite-comedys"),
        "KBC-Видак HD": ("iptvx-noarch", "kbc-vidak"),
        "KBC-ДрамаTic HD": ("iptvx-noarch", "kbc-dramatic"),
        "KLI Horror FHD": ("runigma-iptv", "kli-horror-fhd"),
    }
    for name, (source, source_id) in expected.items():
        assert rows[name]["source"] == source
        assert rows[name]["source_id"] == source_id
