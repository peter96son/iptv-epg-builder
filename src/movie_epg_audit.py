from __future__ import annotations
import csv,gzip,json,os,re,urllib.request
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"output"
GROUPS={"Кино","USSR","Кинозалы","Кино 4K"}
WORKER=os.environ.get("WORKER_PLAYLIST_URL","https://private-uhf-playlist.peter96son.workers.dev/tv?fresh=1")

def parse_time(s):
    m=re.match(r"(\\d{12,14})(?:\\s*([+-]\\d{4}))?",s or "")
    if not m:return None
    raw=m.group(1); fmt="%Y%m%d%H%M%S" if len(raw)==14 else "%Y%m%d%H%M"
    try:d=datetime.strptime(raw,fmt)
    except ValueError:return None
    off=m.group(2); mins=0
    if off:
        mins=(1 if off[0]=="+" else -1)*(int(off[1:3])*60+int(off[3:5]))
    return d.replace(tzinfo=timezone(timedelta(minutes=mins))).astimezone(timezone.utc)

def playlist():
    req=urllib.request.Request(WORKER,headers={"User-Agent":"movie-epg-audit/1.0"})
    text=urllib.request.urlopen(req,timeout=90).read().decode("utf-8","replace")
    out=[]; cur=None
    for line in text.splitlines():
        if line.startswith("#EXTINF"):
            attrs=dict(re.findall(r'([\\w-]+)="([^"]*)"',line))
            cur={"name":line.split(",",1)[1].strip() if "," in line else "",
                 "tvg_id":attrs.get("tvg-id",""),"group":attrs.get("group-title","")}
        elif line.startswith("#EXTGRP:") and cur:
            cur["group"]=line[8:].strip(); out.append(cur); cur=None
    return out

def main():
    with gzip.open(OUT/"epg.xml.gz","rb") as f: root=ET.parse(f).getroot()
    epg_ids={x.attrib.get("id","") for x in root.findall("channel")}
    ps={}
    for p in root.findall("programme"): ps.setdefault(p.attrib.get("channel",""),[]).append(p)
    now=datetime.now(timezone.utc)
    rows=[]
    for c in playlist():
        if c["group"] not in GROUPS: continue
        cid=c["tvg_id"]; arr=ps.get(cid,[])
        current=[]; future=[]
        for p in arr:
            st=parse_time(p.attrib.get("start")); en=parse_time(p.attrib.get("stop"))
            if st and en and st<=now<en: current.append(p)
            if st and st>now: future.append(p)
        issues=[]
        if not cid: issues.append("NO_TVG_ID")
        elif cid not in epg_ids: issues.append("ID_NOT_IN_EPG")
        elif not arr: issues.append("NO_PROGRAMMES")
        elif not current: issues.append("NO_CURRENT_PROGRAMME")
        if cid and arr and not future: issues.append("NO_NEXT_PROGRAMME")
        rows.append({"group":c["group"],"playlist_name":c["name"],"tvg_id":cid,
                     "programme_count":len(arr),"current":len(current),"future":len(future),
                     "status":"OK" if not issues else ";".join(issues)})
    gaps=[r for r in rows if r["status"]!="OK"]
    fields=["group","playlist_name","tvg_id","programme_count","current","future","status"]
    for name,data in [("movie-epg-audit.csv",rows),("movie-epg-gaps.csv",gaps)]:
        with (OUT/name).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)
    summary={"groups":sorted(GROUPS),"channels":len(rows),"ok":len(rows)-len(gaps),"gaps":len(gaps),
             "issues":dict(Counter(i for r in gaps for i in r["status"].split(";")))}
    (OUT/"movie-epg-audit.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    # Strict gate only for mapped channels that have no current programme.
    fatal=[r for r in gaps if r["tvg_id"] and ("ID_NOT_IN_EPG" in r["status"] or "NO_PROGRAMMES" in r["status"] or "NO_CURRENT_PROGRAMME" in r["status"])]
    if fatal:
        raise SystemExit(f"MOVIE EPG QA FAILED: {len(fatal)} mapped movie channels have no usable current EPG. See output/movie-epg-gaps.csv")
if __name__=="__main__": main()
