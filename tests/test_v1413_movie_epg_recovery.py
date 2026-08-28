from types import SimpleNamespace
from pathlib import Path
from src.matcher import Matcher

class Source:
    def __init__(self,name,ids):
        self.name=name
        self.channels={i:object() for i in ids}
        self.names={}

def test_source_pin_names_are_case_insensitive():
    aliases=[{"enabled":"1","playlist_name":"BCU New Media 2","source":"iptvx-noarch","source_id":"bcu-action","hard_pin":"1"}]
    m=Matcher(aliases)
    ch=SimpleNamespace(name="BCU NEW MEDIA 2",tvg_id="",tvg_name="",group="Кинозалы")
    sid,method,confidence=m.match(ch,Source("iptvx-noarch",{"bcu-action"}),{})
    assert (sid,method,confidence)==("bcu-action","alias",100)

def test_confirmed_movie_fallbacks_present():
    text=(Path(__file__).resolve().parents[1]/"data"/"source_pins.csv").read_text(encoding="utf-8")
    assert "YOSSO TV Советские фильмы,Xyosso-sovfilm,,,openbox-tsd,yosso-tv-sovetskie-filmi,0" in text
    assert "BOX Remast Plus 4K,,,,openbox-tsd,box-remastplus-4k,0" in text
