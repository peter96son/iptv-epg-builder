
import gzip,json
import xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
import src.live_ocr_epg_overlay as o

def test_clean_title():
    assert o._clean_title("12 стульев(19")=="12 стульев"

def test_state_tracks_change():
    state={}
    p1={"generated_at":"2026-09-03T10:00:00+00:00","channels":{"x":{
        "group":"Кинозалы","provider_name":"DITV ФИЛЬМЫ",
        "recognized_title":{"title":"Горько","confidence":"high","engine":"tesseract","zone":"left_bottom_tight","score":20}}}}
    o.update_state_from_probe(state,p1)
    assert state["DITV ФИЛЬМЫ"]["current_title"]=="Горько"
    p2={"generated_at":"2026-09-03T11:00:00+00:00","channels":{"x":{
        "group":"Кинозалы","provider_name":"DITV ФИЛЬМЫ",
        "recognized_title":{"title":"12 стульев(19","confidence":"high","engine":"tesseract","zone":"left_bottom_tight","score":20}}}}
    o.update_state_from_probe(state,p2)
    assert state["DITV ФИЛЬМЫ"]["current_title"]=="12 стульев"
    assert state["DITV ФИЛЬМЫ"]["history"][-1]["title"]=="Горько"

def test_overlay_writes_epg_mapping(tmp_path,monkeypatch):
    out=tmp_path/"output";out.mkdir()
    epg=out/"epg.xml.gz";uhf=out/"uhf-mapping.json"
    with gzip.open(epg,"wb") as f:
        ET.ElementTree(ET.Element("tv")).write(f,encoding="utf-8",xml_declaration=True)
    uhf.write_text(json.dumps({"channels":{"Россия 1":"Xrossia1"}}),encoding="utf-8")
    monkeypatch.setattr(o,"OUTPUT",out);monkeypatch.setattr(o,"EPG",epg);monkeypatch.setattr(o,"UHF",uhf)
    now=datetime(2026,9,3,12,0,tzinfo=timezone.utc)
    state={"DITV ФИЛЬМЫ":{"channel_id":o._synthetic_id("DITV ФИЛЬМЫ"),"current_title":"Горько",
      "current_start":(now-timedelta(minutes=30)).isoformat(),"last_seen":now.isoformat(),"history":[]}}
    result=o.apply_state_to_epg(state,now=now)
    assert result["active"]==1
    with gzip.open(epg,"rb") as f: tree=ET.parse(f)
    cid=o._synthetic_id("DITV ФИЛЬМЫ")
    titles=[p.findtext("title") for p in tree.findall(f"./programme[@channel='{cid}']")]
    assert "Горько" in titles
    assert "Следующая программа уточняется" in titles
    assert json.loads(uhf.read_text())["channels"]["DITV ФИЛЬМЫ"]==cid
