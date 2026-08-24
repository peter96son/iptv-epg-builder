from __future__ import annotations
import csv, gzip, json, os, re, urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

from .playlist import parse_m3u

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
GROUPS = {"Кино", "USSR", "Кинозалы", "Кино 4K"}

def _fetch_text(url: str) -> str:
    req=urllib.request.Request(url,headers={"User-Agent":"iptv-movie-qa/13.23"})
    with urllib.request.urlopen(req,timeout=90) as r:
        return r.read().decode("utf-8","replace")

def _parse_ts(value: str):
    m=re.match(r"(\d{12,14})(?:\s*([+-]\d{4}))?", value or "")
    if not m:
        return None
    raw=m.group(1)
    fmt="%Y%m%d%H%M%S" if len(raw)==14 else "%Y%m%d%H%M"
    try:
        d=datetime.strptime(raw,fmt)
    except ValueError:
        return None
    off=m.group(2)
    if off:
        sign=1 if off[0]=="+" else -1
        mins=sign*(int(off[1:3])*60+int(off[3:5]))
        d=d.replace(tzinfo=timezone(timedelta(minutes=mins)))
    else:
        d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def _rules():
    try:
        return json.loads((DATA/"playlist_rules.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

def run(strict: bool=False):
    playlist_url=os.environ.get("PLAYLIST_URL","").strip()
    if not playlist_url:
        raise SystemExit("movie QA: PLAYLIST_URL is missing")
    raw_channels=parse_m3u(_fetch_text(playlist_url))
    rules=_rules()
    excluded=set(rules.get("exclude_groups",[]) or [])
    group_overrides=rules.get("group_overrides",{}) or {}
    name_overrides=rules.get("name_overrides",{}) or {}

    mapping_payload=json.loads((OUTPUT/"uhf-mapping.json").read_text(encoding="utf-8"))
    mapping=mapping_payload.get("channels",{})

    with gzip.open(OUTPUT/"epg.xml.gz","rb") as f:
        root=ET.parse(f).getroot()
    epg_ids={c.get("id","") for c in root.findall("channel")}
    programmes={}
    for p in root.findall("programme"):
        programmes.setdefault(p.get("channel",""),[]).append(p)

    now=datetime.now(timezone.utc)
    rows=[]
    for ch in raw_channels:
        original_group=ch.group
        if original_group in excluded:
            continue
        final_group=group_overrides.get(ch.name, original_group)
        if final_group not in GROUPS:
            continue
        final_name=name_overrides.get(ch.name,ch.name)
        cid=str(mapping.get(ch.name,"") or "")
        arr=programmes.get(cid,[]) if cid else []
        current=[]; future=[]
        for p in arr:
            st=_parse_ts(p.get("start","")); en=_parse_ts(p.get("stop",""))
            if st and en and st <= now < en:
                current.append(p)
            if st and st > now:
                future.append(p)
        issues=[]
        if not cid:
            issues.append("NO_MAPPING")
        elif cid not in epg_ids:
            issues.append("ID_NOT_IN_EPG")
        elif not arr:
            issues.append("NO_PROGRAMMES")
        elif not current:
            issues.append("NO_CURRENT_PROGRAMME")
        if cid and arr and not future:
            issues.append("NO_NEXT_PROGRAMME")
        rows.append({
            "group":final_group,
            "playlist_name":final_name,
            "provider_name":ch.name,
            "provider_tvg_id":ch.tvg_id,
            "output_tvg_id":cid,
            "programme_count":len(arr),
            "current_count":len(current),
            "future_count":len(future),
            "status":"OK" if not issues else ";".join(issues),
        })

    gaps=[r for r in rows if r["status"]!="OK"]
    fields=["group","playlist_name","provider_name","provider_tvg_id","output_tvg_id",
            "programme_count","current_count","future_count","status"]
    for fn,data in (("movie-epg-audit.csv",rows),("movie-epg-gaps.csv",gaps)):
        with (OUTPUT/fn).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)

    summary={
        "checked_at_utc":now.isoformat(),
        "groups":sorted(GROUPS),
        "channels":len(rows),
        "ok":len(rows)-len(gaps),
        "gaps":len(gaps),
        "issue_counts":dict(Counter(
            issue for r in gaps for issue in r["status"].split(";")
        )),
        "group_counts":{
            g:{
                "channels":sum(r["group"]==g for r in rows),
                "ok":sum(r["group"]==g and r["status"]=="OK" for r in rows),
                "gaps":sum(r["group"]==g and r["status"]!="OK" for r in rows),
            } for g in sorted(GROUPS)
        },
    }
    (OUTPUT/"movie-epg-audit.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

    if strict and gaps:
        preview=", ".join(r["playlist_name"] for r in gaps[:12])
        raise SystemExit(
            f"MOVIE EPG QA FAILED: {len(gaps)} gaps remain in movie groups. "
            f"Nothing should be published. First gaps: {preview}. "
            f"See output/movie-epg-gaps.csv"
        )
    return summary

if __name__=="__main__":
    run(strict=False)
