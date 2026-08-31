from __future__ import annotations
import csv,gzip,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"output"

VERIFIED={
 "BCU СССР HD":{"source":"iptvx-noarch","source_id":"bcu-sssr","forbidden":{"bcu-sssr-hdr"}},
 "KLI СССР HD":{"source":"klimedia-dedicated","source_id":"kli-sssr-hd","forbidden":set()},
 "Premium HD":{"source":"premiere-group-dedicated","source_id":"premium-hd","forbidden":set()},
}

def _ts(value):
    value=(value or "").strip()
    if not value:return None
    head=value.split()[0]
    tail=value[len(head):].strip()
    fmt="%Y%m%d%H%M%S" if len(head)>=14 else "%Y%m%d%H%M"
    dt=datetime.strptime(head[:14] if len(head)>=14 else head[:12],fmt)
    if tail and len(tail)>=5 and tail[0] in "+-":
        sign=1 if tail[0]=="+" else -1
        mins=sign*(int(tail[1:3])*60+int(tail[3:5]))
        return dt.replace(tzinfo=timezone(timedelta(minutes=mins))).astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)

def build(now=None,strict=True):
    now=now or datetime.now(timezone.utc)
    with (OUT/"mapping.csv").open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    ids={r.get("output_tvg_id","") for r in rows if r.get("output_tvg_id")}
    live={cid:{"now":None,"next":None} for cid in ids}
    with gzip.open(OUT/"epg.xml.gz","rb") as f:
        for _,e in ET.iterparse(f,events=("end",)):
            if e.tag.split("}")[-1]!="programme":
                e.clear(); continue
            cid=e.get("channel","")
            if cid in ids:
                start=_ts(e.get("start","")); stop=_ts(e.get("stop",""))
                item={"title":e.findtext("title") or "","start":e.get("start",""),"stop":e.get("stop","")}
                if start and stop and start<=now<stop:
                    live[cid]["now"]=item
                elif start and start>now:
                    old=live[cid]["next"]
                    if old is None or _ts(old["start"])>start:
                        live[cid]["next"]=item
            e.clear()
    errors=[]; result=[]
    for r in rows:
        q=dict(r); q.update(live.get(r.get("output_tvg_id"),{"now":None,"next":None}))
        v=VERIFIED.get(r.get("playlist_name",""))
        if v:
            ok=(r.get("source")==v["source"] and r.get("source_id")==v["source_id"] and r.get("source_id") not in v["forbidden"])
            q["verified_binding_ok"]=ok
            if not ok:
                errors.append(f'{r.get("playlist_name")}: expected {v["source"]}/{v["source_id"]}, got {r.get("source")}/{r.get("source_id")}')
        result.append(q)
    payload={"generated_at":now.isoformat(),"channels":result,"verified_errors":errors}
    OUT.mkdir(exist_ok=True)
    (OUT/"epg-live-audit.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"epg-live-audit.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        w.writerow(["playlist_name","group","source","source_id","output_tvg_id","now","next","verified_binding_ok"])
        for r in result:
            w.writerow([r.get("playlist_name",""),r.get("group",""),r.get("source",""),r.get("source_id",""),r.get("output_tvg_id",""),(r.get("now") or {}).get("title",""),(r.get("next") or {}).get("title",""),r.get("verified_binding_ok","")])
    if strict and errors:
        raise SystemExit("Verified EPG binding failure:\n"+"\n".join(errors))
    return payload

if __name__=="__main__":
    p=build()
    print(f'EPG live audit: {len(p["channels"])} channels; verified errors={len(p["verified_errors"])}')
