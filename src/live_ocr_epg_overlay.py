
from __future__ import annotations
import gzip, hashlib, json, re, shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"output"
PROBE=OUTPUT/"movie-gap-live-probe.json"
STATE=OUTPUT/"live-ocr-epg-state.json"
EPG=OUTPUT/"epg.xml.gz"
UHF=OUTPUT/"uhf-mapping.json"
VERIFICATION=OUTPUT/"live-epg-verification-state.json"

TARGET_GROUPS={"Кино","USSR","Кинозалы","Кино 4K"}
VALID_CONFIDENCE={"high","medium"}
STALE_AFTER=timedelta(hours=2,minutes=10)

def _norm(v):
    return re.sub(r"\s+"," ",str(v or "").strip()).casefold().replace("ё","е")

def _synthetic_id(name):
    return "ocr-"+hashlib.sha1(_norm(name).encode("utf-8")).hexdigest()[:14]

def _parse_iso(v):
    try:
        d=datetime.fromisoformat(str(v or "").replace("Z","+00:00"))
    except Exception:
        return None
    if d.tzinfo is None:
        d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def _xmltv_ts(d):
    return d.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S +0000")

def _clean_title(v):
    s=re.sub(r"\s+"," ",str(v or "")).strip(" \t\r\n-—–|")
    s=re.sub(r"\s*\(\s*\d{1,3}\s*$","",s).rstrip()
    return s[:100]

def _load_json(path,default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _load_state():
    x=_load_json(STATE,{})
    return x if isinstance(x,dict) else {}

def _read_probe():
    x=_load_json(PROBE,{})
    return x if isinstance(x,dict) else {}

def update_state_from_probe(state,probe):
    observed=_parse_iso(probe.get("generated_at")) or datetime.now(timezone.utc)
    accepted=changed=0
    for row in (probe.get("channels") or {}).values():
        if not isinstance(row,dict) or row.get("group") not in TARGET_GROUPS:
            continue
        chosen=row.get("recognized_title")
        if not isinstance(chosen,dict) or chosen.get("confidence") not in VALID_CONFIDENCE:
            continue
        name=(row.get("provider_name") or row.get("playlist_name") or "").strip()
        title=_clean_title(chosen.get("title"))
        if not name or len(title)<3:
            continue
        item=state.get(name) if isinstance(state.get(name),dict) else {}
        prev=_clean_title(item.get("current_title"))
        if prev and _norm(prev)==_norm(title):
            start=_parse_iso(item.get("current_start")) or observed-timedelta(minutes=10)
        else:
            if prev:
                hist=item.get("history") if isinstance(item.get("history"),list) else []
                hist.append({
                    "title":prev,
                    "start":(_parse_iso(item.get("current_start")) or observed-timedelta(hours=1)).isoformat(),
                    "stop":observed.isoformat()
                })
                item["history"]=hist[-24:]
                changed+=1
            start=observed-timedelta(minutes=10)
        item.update({
            "channel_id":_synthetic_id(name),
            "channel_name":name,
            "group":row.get("group",""),
            "current_title":title,
            "current_start":start.isoformat(),
            "last_seen":observed.isoformat(),
            "confidence":chosen.get("confidence",""),
            "score":chosen.get("score",0),
            "engine":chosen.get("engine",""),
            "zone":chosen.get("zone","")
        })
        state[name]=item
        accepted+=1
    return {"accepted":accepted,"changed":changed}

def _programme(cid,title,start,stop,desc):
    p=ET.Element("programme",{"channel":cid,"start":_xmltv_ts(start),"stop":_xmltv_ts(stop)})
    ET.SubElement(p,"title",{"lang":"ru"}).text=title
    ET.SubElement(p,"desc",{"lang":"ru"}).text=desc
    return p

def apply_state_to_epg(state,now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not EPG.exists():
        return {"active":0,"applied":0,"error":"epg-missing"}
    with gzip.open(EPG,"rb") as f:
        tree=ET.parse(f)
    root=tree.getroot()

    active={}
    for name,item in state.items():
        if not isinstance(item,dict):
            continue
        seen=_parse_iso(item.get("last_seen"))
        title=_clean_title(item.get("current_title"))
        cid=item.get("channel_id") or _synthetic_id(name)
        if seen and title and now-seen<=STALE_AFTER:
            active[name]=(item,cid,seen,title)

    known_ids={str(i.get("channel_id","")) for i in state.values()
               if isinstance(i,dict) and i.get("channel_id")}
    for elem in list(root):
        if elem.tag=="channel" and elem.get("id") in known_ids:
            root.remove(elem)
        elif elem.tag=="programme" and elem.get("channel") in known_ids:
            root.remove(elem)

    for name,(item,cid,seen,title) in active.items():
        ch=ET.Element("channel",{"id":cid})
        ET.SubElement(ch,"display-name").text=name
        root.append(ch)

        for old in item.get("history",[]) if isinstance(item.get("history"),list) else []:
            st=_parse_iso(old.get("start")); en=_parse_iso(old.get("stop")); ot=_clean_title(old.get("title"))
            if st and en and ot and en>now-timedelta(hours=12) and en>st:
                root.append(_programme(cid,ot,st,en,"Название восстановлено по надписи в эфире канала."))

        start=_parse_iso(item.get("current_start")) or seen-timedelta(minutes=10)
        stop=max(now+timedelta(minutes=5),seen+timedelta(minutes=75))
        root.append(_programme(cid,title,start,stop,"Текущее название распознано непосредственно из видеопотока."))
        root.append(_programme(cid,"Следующая программа уточняется",stop,stop+timedelta(hours=2),
                               "Следующее название появится после следующего распознавания эфира."))

    tmp=OUTPUT/"epg.xml.ocr.tmp"
    tree.write(tmp,encoding="utf-8",xml_declaration=True)
    with tmp.open("rb") as src, EPG.open("wb") as raw:
        with gzip.GzipFile(filename="epg.xml",mode="wb",fileobj=raw,mtime=0,compresslevel=9) as dst:
            shutil.copyfileobj(src,dst)
    tmp.unlink()

    mapping=_load_json(UHF,{"generated_at":"","channels":{}})
    if not isinstance(mapping,dict):
        mapping={"generated_at":"","channels":{}}
    channels=mapping.get("channels")
    if not isinstance(channels,dict):
        channels={}
        mapping["channels"]=channels

    for name,item in state.items():
        if isinstance(item,dict) and str(channels.get(name,"")).startswith("ocr-"):
            channels.pop(name,None)
    for name,(_item,cid,_seen,_title) in active.items():
        channels[name]=cid

    mapping["generated_at"]=now.isoformat()
    mapping["ocr_overlay_channels"]=len(active)
    UHF.write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"active":len(active),"applied":len(active)}

def _merge_confirmed_mismatches(state):
    verification=_load_json(VERIFICATION,{})
    channels=verification.get("channels",{}) if isinstance(verification,dict) else {}
    merged=0
    observed=datetime.now(timezone.utc)
    for name,item in channels.items():
        if not isinstance(item,dict) or item.get("status")!="MISMATCH_CONFIRMED":
            continue
        title=_clean_title(item.get("ocr_title"))
        if not title:
            continue
        existing=state.get(name) if isinstance(state.get(name),dict) else {}
        prev=_clean_title(existing.get("current_title"))
        start=_parse_iso(existing.get("current_start")) if prev and _norm(prev)==_norm(title) else None
        start=start or observed-timedelta(minutes=10)
        existing.update({
            "channel_id":_synthetic_id(name),
            "channel_name":name,
            "current_title":title,
            "current_start":start.isoformat(),
            "last_seen":observed.isoformat(),
            "confidence":item.get("ocr_confidence","high"),
            "source":"confirmed-live-mismatch",
        })
        state[name]=existing
        merged+=1
    return merged


def run(*,consume_probe=True,now=None):
    state=_load_state()
    probe_result={"accepted":0,"changed":0}
    if consume_probe and PROBE.exists():
        probe_result=update_state_from_probe(state,_read_probe())
        STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    mismatch_overrides=_merge_confirmed_mismatches(state)
    if mismatch_overrides:
        STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    overlay=apply_state_to_epg(state,now=now)
    result={"probe":probe_result,"confirmed_mismatch_overrides":mismatch_overrides,"overlay":overlay}
    print("[live-ocr-epg] "+json.dumps(result,ensure_ascii=False),flush=True)
    return result

if __name__=="__main__":
    run()
