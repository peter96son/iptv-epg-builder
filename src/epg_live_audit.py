from __future__ import annotations
import csv,gzip,json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"output"
DATA=ROOT/"data"

STRICT_VERIFIED={
    "BCU СССР HD":{"source":"iptvx-noarch","source_id":"bcu-sssr","forbidden":{"bcu-sssr-hdr"}},
    "KLI СССР HD":{"source":"klimedia-dedicated","source_id":"kli-sssr-hd","forbidden":set()},
}

# Backward-compatible public name used by existing regression tests and older
# tooling. Keep this alias stable even though policy-aware channels are no
# longer hard-coded here.
VERIFIED=STRICT_VERIFIED

def _enabled(value):
    return str(value if value is not None else "1").strip().lower() not in {"0","false","no","off"}

def _policy_bindings(path=None):
    path=path or DATA/"source_policy_v15.csv"
    if not path.exists():
        return {}
    out={}
    with path.open(encoding="utf-8-sig",newline="") as f:
        for row in csv.DictReader(f):
            if not _enabled(row.get("enabled","1")):
                continue
            name=(row.get("playlist_name") or "").strip()
            source=(row.get("source") or "").strip()
            sid=(row.get("source_id") or "").strip()
            if name and source and sid:
                out.setdefault(name,set()).add((source,sid))
    return out

def _ts(value):
    value=(value or "").strip()
    if not value:return None
    m=re.match(r"^(\d{12,})(?:\s*([+-]\d{4}|Z))?",value)
    if not m:return None
    digits=m.group(1);zone=m.group(2) or ""
    try:
        dt=datetime.strptime(digits[:14],"%Y%m%d%H%M%S") if len(digits)>=14 else datetime.strptime(digits[:12],"%Y%m%d%H%M")
    except (ValueError,TypeError):
        return None
    if zone=="Z":return dt.replace(tzinfo=timezone.utc)
    if zone:
        sign=1 if zone[0]=="+" else -1
        mins=sign*(int(zone[1:3])*60+int(zone[3:5]))
        return dt.replace(tzinfo=timezone(timedelta(minutes=mins))).astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)

def build(now=None,strict=True):
    now=now or datetime.now(timezone.utc)
    policy=_policy_bindings()
    with (OUT/"mapping.csv").open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    ids={r.get("output_tvg_id","") for r in rows if r.get("output_tvg_id")}
    live={cid:{"now":None,"next":None} for cid in ids}
    with gzip.open(OUT/"epg.xml.gz","rb") as f:
        for _,e in ET.iterparse(f,events=("end",)):
            if e.tag.split("}")[-1]!="programme":
                e.clear();continue
            cid=e.get("channel","")
            if cid in ids:
                start=_ts(e.get("start","")); stop=_ts(e.get("stop",""))
                item={"title":e.findtext("title") or "","start":e.get("start",""),"stop":e.get("stop","")}
                if start and stop and start<=now<stop:
                    live[cid]["now"]=item
                elif start and start>now:
                    old=live[cid]["next"]
                    if old is None or _ts(old["start"]) is None or _ts(old["start"])>start:
                        live[cid]["next"]=item
            e.clear()

    errors=[]; result=[]
    for r in rows:
        q=dict(r)
        q.update(live.get(r.get("output_tvg_id"),{"now":None,"next":None}))
        name=r.get("playlist_name","")
        pair=(r.get("source",""),r.get("source_id",""))
        strict_v=STRICT_VERIFIED.get(name)
        if strict_v:
            ok=pair==(strict_v["source"],strict_v["source_id"]) and r.get("source_id") not in strict_v["forbidden"]
            q["verified_binding_ok"]=ok
            q["binding_rule"]="strict-verified"
            if not ok:
                errors.append(f'{name}: expected {strict_v["source"]}/{strict_v["source_id"]}, got {pair[0]}/{pair[1]}')
        elif name in policy:
            ok=pair in policy[name]
            q["verified_binding_ok"]=ok
            q["binding_rule"]="v15-policy"
            if not ok:
                allowed=", ".join(f"{s}/{sid}" for s,sid in sorted(policy[name]))
                errors.append(f"{name}: binding {pair[0]}/{pair[1]} outside v15 policy; allowed: {allowed}")
        else:
            q["verified_binding_ok"]=""
            q["binding_rule"]=""

        if (strict_v or name in policy) and q.get("verified_binding_ok") is True and q.get("now") is None:
            q["verified_binding_ok"]=False
            errors.append(f"{name}: allowed binding {pair[0]}/{pair[1]} has no NOW programme")
        result.append(q)

    payload={"generated_at":now.isoformat(),"channels":result,"verified_errors":errors}
    (OUT/"epg-live-audit.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"epg-live-audit.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f)
        w.writerow(["playlist_name","group","source","source_id","output_tvg_id","now","next","verified_binding_ok","binding_rule"])
        for r in result:
            w.writerow([r.get("playlist_name",""),r.get("group",""),r.get("source",""),r.get("source_id",""),r.get("output_tvg_id",""),(r.get("now")or{}).get("title",""),(r.get("next")or{}).get("title",""),r.get("verified_binding_ok",""),r.get("binding_rule","")])
    if strict and errors:
        raise SystemExit("Verified EPG binding failure:\n"+"\n".join(errors))
    return payload

if __name__=="__main__":
    p=build()
    print(f'EPG live audit: {len(p["channels"])} channels; verified errors={len(p["verified_errors"])}')
