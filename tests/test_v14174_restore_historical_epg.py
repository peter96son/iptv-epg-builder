import csv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def pins():
    with (ROOT/"data/source_pins.csv").open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def test_current_verified_movie_epg_bindings_are_locked():
    rows=pins()
    required={
      ("USSR HD","Xussr-premieregroup","gabbarit-primary","USSR HD","0"),
      ("Premium HD","Xpremium-hd","premiere-group-dedicated","premium-hd","1"),
      ("Premiere HD","Xpremiere-hd","gabbarit-primary","Premiere HD","0"),
      ("Thriller HD","Xthriller-hd","openbox-tsd","thriller-hd","1"),
      ("РуКино HD","Xrukino-hd","iptv-online-primary","Xklirussian","1"),
      ("Paradise HD","Xparadise-hd","gabbarit-primary","Paradise HD","0"),
      ("Paradox HD","Xparadox-hd","gabbarit-primary","Paradox HD","0"),
      ("VeleS Вестерн","veles-vestern","openbox-tsd","veles-vestern","1"),
      ("VeleS С Новым годом!","velesyear-new","runigma-iptv","veles-newyear","1"),
    }
    actual={(r["playlist_name"],r["playlist_tvg_id"],r["source"],r["source_id"],r["hard_pin"]) for r in rows}
    assert required <= actual

def test_gabbarit_is_fallback_not_duplicate_hard_pin():
    assert not any(r["source"].startswith("gabbarit") and r["hard_pin"]=="1" for r in pins())
