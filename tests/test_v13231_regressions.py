import csv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def pins():
    with (ROOT/"data/source_pins.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def test_veles_movie_hits_primary_pin_stays_runigma():
    rows={r["playlist_name"]:r for r in pins()}
    assert rows["VeleS Movie Hits"]["source"]=="runigma-iptv"
    assert rows["VeleS Movie Hits"]["source_id"]=="veles-movie-hits"

def test_gabbarit_is_not_encoded_as_duplicate_hard_pin():
    assert not any(
        r["source"].startswith("gabbarit") and r["hard_pin"]=="1"
        for r in pins()
    )

def test_movie_audit_is_nonblocking_by_default():
    text=(ROOT/"src/movie_epg_audit.py").read_text(encoding="utf-8")
    assert "def run(strict: bool=False):" in text
    assert "run(strict=False)" in text
