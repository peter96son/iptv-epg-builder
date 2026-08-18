
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_kli_feed_precedes_runigma():
    sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in sources]
    assert names.index("klimedia-dedicated") < names.index("runigma-iptv")
    kli = next(s for s in sources if s["name"] == "klimedia-dedicated")
    assert kli["url"] == "https://epg.klimedia.pro"

def test_portugal_feed_and_aliases_exist():
    sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
    pt = next(s for s in sources if s["name"] == "epgshare-PT")
    assert pt["url"].endswith("epg_ripper_PT1.xml.gz")
    with (ROOT / "data" / "aliases.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    lookup = {(r["playlist_name"], r["source"]): r["source_id"] for r in rows}
    assert lookup[("SPORT TV 1 PT", "epgshare-PT")] == "SPORT.TV1.HD.pt"
    assert lookup[("DAZN 1 PT", "epgshare-PT")] == "DAZN.1.pt"
    assert lookup[("Canal 11 International", "epgshare-PT")] == "Canal.11.HD.pt"
