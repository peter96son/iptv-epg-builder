from __future__ import annotations
import csv,gzip,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"output"
VERIFIED={"BCU СССР HD":{"source":"iptvx-noarch","source_id":"bcu-sssr","forbidden":{"bcu-sssr-hdr"}},"KLI СССР HD":{"source":"klimedia-dedicated","source_id":"kli-sssr-hd","forbidden":set()},"Premium HD":{"source":"premiere-group-dedicated","source_id":"premium-hd","forbidden":set()}}
def ts(v):
 v=(v or "").strip(); h=v.split()[0]; z=v[len(h):].strip()
 if not h:return None
 f="%Y%m%d%H%M%S" if len(h)>=14 else "%Y%m%d%H%M"; d=datetime.strptime(h[:14] if len(h)>=14 else h[:12],f)
 if z and z[0] in "+-":
  m=(int(z[1:3])*60+int(z[3:5]))*(1 if z[0]=="+" else -1); return d.replace(tzinfo=timezone(timedelta(minutes=m))).astimezone(timezone.utc)
 return d.replace(tzinfo=timezone.utc)
def build(now=None,strict=True):
 now=now or datetime.now(timezone.utc); rows=[]
 with (OUT/"mapping.csv").open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
 ids={r["output_tvg_id"] for r in rows if r.get("output_tvg_id")}; p={i:{"now":None,"next":None} for i in ids}
 with gzip.open(OUT/"epg.xml.gz","rb") as f:
  for _,e in ET.iterparse(f,events=("end",)):
   if e.tag.split("}")[-1]!="programme": e.clear(); continue
   cid=e.get("channel","")
   if cid in ids:
    s,st=ts(e.get("start")),ts(e.get("stop")); item={"title":e.findtext("title") or "","start":e.get("start",""),"stop":e.get("stop","")}
    if s and st and s<=now<st:p[cid]["now"]=item
    elif s and s>now and (p[cid]["next"] is None or ts(p[cid]["next"]["start"])>s):p[cid]["next"]=item
   e.clear()
 errors=[]; result=[]
 for r in rows:
  q=dict(r); q.update(p.get(r.get("output_tvg_id"),{"now":None,"next":None}))
  if r["playlist_name"] in VERIFIED:
   v=VERIFIED[r["playlist_name"]]; ok=r["source"]==v["source"] and r["source_id"]==v["source_id"] and r["source_id"] not in v["forbidden"]; q["verified_binding_ok"]=ok
   if not ok:errors.append(f'{r["playlist_name"]}: expected {v["source"]}/{v["source_id"]}, got {r["source"]}/{r["source_id"]}')
  result.append(q)
 payload={"generated_at":now.isoformat(),"channels":result,"verified_errors":errors}; OUT.mkdir(exist_ok=True)
 (OUT/"epg-live-audit.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 with (OUT/"epg-live-audit.csv").open("w",encoding="utf-8",newline="") as f:
  w=csv.writer(f);w.writerow(["playlist_name","source","source_id","output_tvg_id","now","next","verified_binding_ok"])
  for r in result:w.writerow([r["playlist_name"],r["source"],r["source_id"],r["output_tvg_id"],(r.get("now")or{}).get("title",""),(r.get("next")or{}).get("title",""),r.get("verified_binding_ok","")])
 if strict and errors:raise SystemExit("Verified EPG binding failure:\n"+"\n".join(errors))
 return payload
if __name__=="__main__":
 x=build();print(f'EPG live audit: {len(x["channels"])} channels; verified errors={len(x["verified_errors"])}')
