import csv, json
from pathlib import Path

def pins():
    with Path("data/source_pins.csv").open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def test_fresh_has_fallback_sources():
    rows=pins()
    names=["Fresh Fantastic","Fresh VHS","Fresh Rating","Fresh Family","Fresh Premiere",
           "Fresh Comedy","Fresh Kids","Fresh Cinema","Fresh Horror","Fresh Adventure",
           "Fresh Romantic","Fresh Russian","Fresh Thriller"]
    for name in names:
        rr=[r for r in rows if r["playlist_name"]==name]
        assert {r["source"] for r in rr} == {"iptvx-noarch","openbox-tsd"}

def test_fresh_romantic_provider_ids():
    rr={r["source"]:r["source_id"] for r in pins() if r["playlist_name"]=="Fresh Romantic"}
    assert rr["iptvx-noarch"]=="fresh-romatic"
    assert rr["openbox-tsd"]=="fresh-romantic"

def test_magic_has_fallback_sources():
    rows=pins()
    for part in ["Premiere","Adventure","Russian","Action","Comedy","Family","Galaxy",
                 "Horror","Karate","Love","Thriller","VHS","Disney"]:
        rr=[r for r in rows if r["playlist_name"]==f"Magic {part}"]
        assert {r["source"] for r in rr} == {"iptvx-noarch","openbox-tsd"}

def test_veles_and_dj():
    rows={r["playlist_name"]:r for r in pins() if r["playlist_name"]=="VeleS Movie Hits"}
    assert rows["VeleS Movie Hits"]["source"]=="runigma-iptv"
    assert rows["VeleS Movie Hits"]["source_id"]=="veles-movie-hits"
    rules=json.loads(Path("data/playlist_rules.json").read_text(encoding="utf-8"))
    assert rules["group_overrides"]["VeleS Dj Set"]=="Музыкальные"
