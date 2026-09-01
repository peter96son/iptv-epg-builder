import csv
from pathlib import Path

def test_restored_missing_historical_fallbacks():
    p=Path(__file__).resolve().parents[1]/"data"/"source_pins.csv"
    with p.open(encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    required={
      ("USSR HD","Xussr-premieregroup","gabbarit-primary","USSR HD","0"),
      ("Premiere HD","Xpremiere-hd","gabbarit-primary","Premiere HD","0"),
      ("Paradise HD","Xparadise-hd","gabbarit-primary","Paradise HD","0"),
      ("Paradox HD","Xparadox-hd","gabbarit-primary","Paradox HD","0"),
      ("VeleS Вестерн","veles-vestern","openbox-tsd","veles-vestern","1"),
    }
    actual={(r["playlist_name"],r["playlist_tvg_id"],r["source"],r["source_id"],r["hard_pin"]) for r in rows}
    assert required <= actual
