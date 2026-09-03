from __future__ import annotations
import csv,gzip,json,os,re,subprocess,tempfile,xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.request import Request,urlopen
from .movie_gap_live_probe import _find_exact,_load_profiles,_ocr_frame,_parse_m3u,_pick_title

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"output"; AUDIT=OUTPUT/"movie-epg-audit.csv"; EPG=OUTPUT/"epg.xml.gz"
RESULT=OUTPUT/"live-epg-verification.json"; STATE=OUTPUT/"live-epg-verification-state.json"
TARGET_GROUPS={"Кино","USSR","Кинозалы","Кино 4K"}
MAX_PER_RUN=max(20,min(600,int(os.environ.get("LIVE_EPG_VERIFY_MAX","250"))))
WORKERS=max(2,min(24,int(os.environ.get("LIVE_EPG_VERIFY_WORKERS","12"))))
MATCH_THRESHOLD=float(os.environ.get("LIVE_EPG_TITLE_MATCH","0.72"))
CONFIRM_MISMATCHES=max(2,int(os.environ.get("LIVE_EPG_MISMATCH_CONFIRM","2")))
TRUST_AFTER=max(2,int(os.environ.get("LIVE_EPG_TRUST_AFTER","4")))
NO_TITLE_AFTER=max(2,int(os.environ.get("LIVE_EPG_NO_TITLE_AFTER","3")))
TRUST_RECHECK_HOURS=max(24,int(os.environ.get("LIVE_EPG_TRUST_RECHECK_HOURS","168")))
NO_TITLE_RECHECK_HOURS=max(24,int(os.environ.get("LIVE_EPG_NO_TITLE_RECHECK_HOURS","168")))

def _download_playlist(url):
    with urlopen(Request(url,headers={"User-Agent":"IPTV-EPG live verifier"}),timeout=30) as r:
        return r.read().decode("utf-8","replace")

def _parse_ts(value):
    m=re.match(r"(\d{12,14})(?:\s*([+-]\d{4}))?",value or "")
    if not m:return None
    raw=m.group(1); fmt="%Y%m%d%H%M%S" if len(raw)==14 else "%Y%m%d%H%M"
    try:d=datetime.strptime(raw,fmt)
    except ValueError:return None
    off=m.group(2) or "+0000"; sign=1 if off[0]=="+" else -1
    mins=sign*(int(off[1:3])*60+int(off[3:5]))
    return d.replace(tzinfo=timezone(timedelta(minutes=mins))).astimezone(timezone.utc)

def _title_text(p):
    for c in list(p):
        if c.tag.split("}")[-1]=="title" and (c.text or "").strip():return (c.text or "").strip()
    return ""

def _current_titles():
    if not EPG.exists():return {}
    now=datetime.now(timezone.utc)
    with gzip.open(EPG,"rb") as f:root=ET.parse(f).getroot()
    out={}
    for p in root.findall(".//programme"):
        st=_parse_ts(p.get("start","")); en=_parse_ts(p.get("stop",""))
        if st and en and st<=now<en:
            t=_title_text(p)
            if t:out[p.get("channel","")]=t
    return out

def _load_ok_channels():
    if not AUDIT.exists():return []
    with AUDIT.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    return [r for r in rows if (r.get("group") or "").strip() in TARGET_GROUPS and (r.get("status") or "").strip()=="OK" and (r.get("output_tvg_id") or "").strip()]

def _norm_title(v):
    s=str(v or "").casefold().replace("ё","е")
    s=re.sub(r"\(\s*\d{4}\s*\)"," ",s); s=re.sub(r"\b\d{4}\b"," ",s)
    s=re.sub(r"[^a-zа-я0-9]+"," ",s)
    return " ".join(s.split())

def _similarity(a,b):
    a=_norm_title(a); b=_norm_title(b)
    if not a or not b:return 0.0
    if a==b:return 1.0
    if (a in b or b in a) and min(len(a),len(b))>=5:return max(0.84,min(len(a),len(b))/max(len(a),len(b)))
    sa=set(a.split()); sb=set(b.split())
    return max(SequenceMatcher(None,a,b).ratio(),len(sa&sb)/max(1,len(sa|sb)))

def _capture_one(url,d):
    out=d/"verify.png"
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-rw_timeout","8000000","-i",url,"-ss","6","-frames:v","1","-y",str(out)]
    try:p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=18)
    except subprocess.TimeoutExpired:return None
    return out if p.returncode==0 and out.exists() and out.stat().st_size>0 else None

def _load_state():
    if not STATE.exists():return {"cursor":0,"channels":{}}
    try:x=json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:return {"cursor":0,"channels":{}}
    if not isinstance(x,dict):return {"cursor":0,"channels":{}}
    x.setdefault("cursor",0);x.setdefault("channels",{});return x

def _save_state(state):STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def _verify_one(row,playlist,current,profiles):
    provider=(row.get("provider_name") or row.get("playlist_name") or "").strip()
    ch=_find_exact(playlist,provider); epg_title=current.get((row.get("output_tvg_id") or "").strip(),"")
    base={"group":row.get("group",""),"playlist_name":row.get("playlist_name",""),"provider_name":provider,"output_tvg_id":row.get("output_tvg_id",""),"epg_title":epg_title}
    if ch is None:return {**base,"verdict":"STREAM_NOT_FOUND"}
    if not epg_title:return {**base,"verdict":"NO_CURRENT_EPG"}
    profile=profiles.get(provider,{}) if isinstance(profiles,dict) else {}
    with tempfile.TemporaryDirectory(prefix="epg-check-") as td:
        td=Path(td); frame=_capture_one(ch["url"],td)
        if frame is None:return {**base,"verdict":"CAPTURE_FAILED"}
        lines,candidates=_ocr_frame(frame,td,provider,profile)
    chosen=_pick_title(candidates,row.get("playlist_name") or provider,provider,profile)
    if not chosen or chosen.get("confidence") not in {"high","medium"}:
        return {**base,"verdict":"NO_CONFIDENT_OCR","ocr_lines":lines}
    ocr_title=chosen.get("title",""); sim=_similarity(epg_title,ocr_title)
    return {**base,"verdict":"VERIFIED" if sim>=MATCH_THRESHOLD else "MISMATCH","ocr_title":ocr_title,"ocr_confidence":chosen.get("confidence"),"ocr_score":chosen.get("score"),"ocr_engine":chosen.get("engine"),"ocr_zone":chosen.get("zone"),"similarity":round(sim,3)}

def _apply_observation(state,row,now):
    name=row.get("provider_name") or row.get("playlist_name") or ""
    item=state["channels"].get(name,{})
    verdict=row.get("verdict","")
    item.setdefault("verified_streak",0); item.setdefault("no_title_streak",0)
    item.setdefault("mismatch_streak",0); item.setdefault("checks",0)
    item["checks"]=int(item.get("checks",0))+1
    item["last_checked"]=now.isoformat()
    item["output_tvg_id"]=row.get("output_tvg_id",""); item["group"]=row.get("group","")

    if verdict=="VERIFIED":
        item["verified_streak"]=int(item.get("verified_streak",0))+1
        item["mismatch_streak"]=0; item["no_title_streak"]=0
        item["last_verified"]=now.isoformat()
        item["epg_title"]=row.get("epg_title",""); item["ocr_title"]=row.get("ocr_title","")
        item["status"]="TRUSTED" if item["verified_streak"]>=TRUST_AFTER else "VERIFIED"
    elif verdict=="MISMATCH":
        item["verified_streak"]=0; item["no_title_streak"]=0
        same=_norm_title(item.get("epg_title"))==_norm_title(row.get("epg_title")) and _norm_title(item.get("ocr_title"))==_norm_title(row.get("ocr_title"))
        streak=int(item.get("mismatch_streak",0))+1 if same else 1
        item.update({"mismatch_streak":streak,"epg_title":row.get("epg_title",""),"ocr_title":row.get("ocr_title",""),"similarity":row.get("similarity",0),"ocr_confidence":row.get("ocr_confidence",""),"status":"MISMATCH_CONFIRMED" if streak>=CONFIRM_MISMATCHES else "MISMATCH_PENDING","last_mismatch":now.isoformat()})
    elif verdict=="NO_CONFIDENT_OCR":
        item["verified_streak"]=0; item["mismatch_streak"]=0
        item["no_title_streak"]=int(item.get("no_title_streak",0))+1
        item["status"]="NO_ONSCREEN_TITLE" if item["no_title_streak"]>=NO_TITLE_AFTER else "VERIFYING"
        item["last_no_title"]=now.isoformat()
    elif verdict in {"CAPTURE_FAILED","STREAM_NOT_FOUND","NO_CURRENT_EPG","ERROR"}:
        item["last_nondecision"]=verdict
        if not item.get("status"):item["status"]="NEW"
    state["channels"][name]=item
    row["state_status"]=item.get("status",""); row["verified_streak"]=item.get("verified_streak",0)
    row["no_title_streak"]=item.get("no_title_streak",0); row["mismatch_streak"]=item.get("mismatch_streak",0)

def _age_hours(value,now):
    try:
        dt=datetime.fromisoformat(str(value or "").replace("Z","+00:00"))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return max(0.0,(now-dt.astimezone(timezone.utc)).total_seconds()/3600.0)
    except Exception:return 1e9

def _priority_for(row,item,now):
    status=(item or {}).get("status","NEW")
    if status=="MISMATCH_PENDING":return (0,_age_hours(item.get("last_checked"),now))
    if status=="MISMATCH_CONFIRMED":return (1,_age_hours(item.get("last_checked"),now))
    if status in {"NEW",""}:return (2,1e9)
    if status in {"VERIFYING","VERIFIED"}:return (3,_age_hours(item.get("last_checked"),now))
    if status=="NO_ONSCREEN_TITLE":
        age=_age_hours(item.get("last_checked"),now); return (5 if age>=NO_TITLE_RECHECK_HOURS else 9,age)
    if status=="TRUSTED":
        age=_age_hours(item.get("last_checked"),now); return (6 if age>=TRUST_RECHECK_HOURS else 10,age)
    return (7,_age_hours(item.get("last_checked"),now))

def _select_batch(eligible,state,now):
    ranked=[]
    for row in eligible:
        name=(row.get("provider_name") or row.get("playlist_name") or "").strip()
        item=state.get("channels",{}).get(name,{})
        pri,age=_priority_for(row,item,now)
        if pri in {9,10}:continue
        ranked.append((pri,-age,name,row))
    ranked.sort(key=lambda x:(x[0],x[1],x[2]))
    return [x[3] for x in ranked[:MAX_PER_RUN]]

def main():
    url=os.environ.get("PLAYLIST_URL","").strip()
    if not url:raise SystemExit("PLAYLIST_URL missing")
    eligible=_load_ok_channels();state=_load_state();profiles=_load_profiles();playlist=_parse_m3u(_download_playlist(url));current=_current_titles()
    if not eligible:
        RESULT.write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"eligible":0,"checked":0,"results":[]},ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return 0
    now=datetime.now(timezone.utc)
    batch=_select_batch(eligible,state,now)
    from concurrent.futures import ThreadPoolExecutor,as_completed
    results=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs=[pool.submit(_verify_one,r,playlist,current,profiles) for r in batch]
        for f in as_completed(jobs):
            try:results.append(f.result())
            except Exception as exc:results.append({"verdict":"ERROR","error":type(exc).__name__})
    for row in results:
        if row.get("provider_name"):_apply_observation(state,row,now)
    state["updated_at"]=now.isoformat();_save_state(state)
    counts={}
    for item in state.get("channels",{}).values():
        if isinstance(item,dict):counts[item.get("status","NEW")]=counts.get(item.get("status","NEW"),0)+1
    payload={"generated_at":now.isoformat(),"mode":"adaptive validation of channels that already have EPG","eligible":len(eligible),"selected":len(batch),"max_per_run":MAX_PER_RUN,"workers":WORKERS,"match_threshold":MATCH_THRESHOLD,"confirm_mismatches":CONFIRM_MISMATCHES,"trust_after":TRUST_AFTER,"no_title_after":NO_TITLE_AFTER,"state_counts":counts,"results":sorted(results,key=lambda x:x.get("provider_name","")),"confirmed_mismatches":{n:i for n,i in state["channels"].items() if isinstance(i,dict) and i.get("status")=="MISMATCH_CONFIRMED"}}
    RESULT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"eligible":len(eligible),"selected":len(batch),"checked":len(results),"verified":sum(r.get("verdict")=="VERIFIED" for r in results),"mismatches":sum(r.get("verdict")=="MISMATCH" for r in results),"confirmed_total":len(payload["confirmed_mismatches"]),"state_counts":counts},ensure_ascii=False),flush=True);return 0
if __name__=="__main__":raise SystemExit(main())
