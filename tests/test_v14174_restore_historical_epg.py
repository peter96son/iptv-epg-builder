from pathlib import Path

REQUIRED = [
("USSR HD","Xussr-premieregroup","gabbarit-primary","USSR HD"),
("Premium HD","Xpremium-hd","gabbarit-primary","Premium HD"),
("Premiere HD","Xpremiere-hd","gabbarit-primary","Premiere HD"),
("Thriller HD","Xthriller-hd","gabbarit-primary","Thriller HD"),
("РуКино HD","Xrukino-hd","gabbarit-primary","РуКино HD"),
("Paradise HD","Xparadise-hd","gabbarit-primary","Paradise HD"),
("Paradox HD","Xparadox-hd","gabbarit-primary","Paradox HD"),
("VeleS Вестерн","veles-vestern","openbox-tsd","veles-vestern"),
("VeleS С Новым годом!","velesyear-new","gabbarit-primary","VeleS NewYear"),
]

def test_historical_movie_epg_bindings_are_locked():
    rows=(Path(__file__).resolve().parents[1]/"data"/"source_pins.csv").read_text(encoding="utf-8")
    for name,tvg,source,source_id in REQUIRED:
        needle=f"{name},{tvg},,,{source},{source_id}"
        assert needle in rows, needle
