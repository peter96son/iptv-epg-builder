from __future__ import annotations
import csv,hashlib,json,os,re,subprocess,tempfile,threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"output"
TARGET_GROUPS={"Кино","USSR","Кинозалы","Кино 4K"}
GAPS=OUTPUT/"movie-epg-gaps.csv"
RESULT=OUTPUT/"movie-gap-live-probe.json"
PROFILES=OUTPUT/"movie-gap-ocr-profiles.json"
FRAME_SECONDS=(5,25,45)
OCR_LANG=os.environ.get("STREAM_OCR_LANG","rus+eng")
MAX_CHANNELS=max(0,int(os.environ.get("GAP_PROBE_MAX_CHANNELS","0")))
MAX_WORKERS=max(1,min(4,int(os.environ.get("GAP_PROBE_WORKERS","4"))))
_PADDLE=None
_PADDLE_ERROR=None
_PADDLE_INIT_LOCK=threading.Lock()
_PADDLE_RUN_LOCK=threading.Lock()

def _download_playlist(url):
    with urlopen(Request(url,headers={"User-Agent":"IPTV-EPG-Builder gap verifier"}),timeout=30) as r:
        return r.read().decode("utf-8","replace")

def _parse_m3u(text):
    rows=[];info=None
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith("#EXTINF:"):
            attrs=dict(re.findall(r'([\w-]+)="([^"]*)"',line))
            info={"name":line.rsplit(",",1)[-1].strip(),"tvg_id":attrs.get("tvg-id",""),"group":attrs.get("group-title","")}
        elif info and line and not line.startswith("#"):
            row=dict(info);row["url"]=line;rows.append(row);info=None
    return rows

def _load_gaps(path=GAPS):
    if not path.exists():return []
    with path.open(encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
    return [r for r in rows if (r.get("group") or "").strip() in TARGET_GROUPS and (r.get("status") or "").strip() and (r.get("status") or "").strip()!="OK"]

def _norm(value):
    s=(value or "").casefold().replace("ё","е")
    s=re.sub(r"\b(?:fhd|uhd|4k|hd|sd|hevc|h265|h\.265)\b"," ",s)
    s=re.sub(r"[^a-zа-я0-9]+"," ",s)
    return " ".join(s.split())

def _find_exact(rows,name):
    exact=[r for r in rows if r["name"]==name]
    if len(exact)==1:return exact[0]
    n=_norm(name);matches=[r for r in rows if _norm(r["name"])==n]
    return matches[0] if len(matches)==1 else None

def _clean_lines(lines):
    out=[]
    for raw in lines:
        line=re.sub(r"\s+"," ",str(raw or "")).strip(" |_-—–")
        if len(line)<3:continue
        if sum(c.isalnum() for c in line)<max(2,len(line)//3):continue
        if not any(c.isalpha() for c in line):continue
        if line not in out:out.append(line)
    return out

def _redact_metadata(value):
    return re.sub(r"https?://\S+","[URL]",str(value or ""),flags=re.I)[:1000]

def _ffprobe(url):
    cmd=["ffprobe","-v","error","-rw_timeout","10000000","-analyzeduration","6000000","-probesize","6000000","-show_format","-show_programs","-show_streams","-of","json",url]
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=12)
    except subprocess.TimeoutExpired:return {"ok":False,"error":"timeout"}
    if p.returncode:return {"ok":False,"error":"probe-failed"}
    try:data=json.loads(p.stdout)
    except Exception:return {"ok":False,"error":"invalid-json"}
    tags={};wanted={"title","service_name","service_provider","icy-title","icy-name","artist","album","description","comment"}
    def add(obj,prefix):
        for k,v in (obj.get("tags") or {}).items():
            if k.casefold() in wanted:tags[f"{prefix}.{k}"]=_redact_metadata(v)
    add(data.get("format") or {},"format")
    for i,x in enumerate(data.get("programs") or []):add(x,f"program[{i}]")
    for i,x in enumerate(data.get("streams") or []):add(x,f"stream[{i}]")
    return {"ok":True,"metadata":tags}

def _capture_frames(url,directory):
    pattern=directory/"frame-%02d.png"
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-rw_timeout","10000000","-i",url,"-t","49","-vf","fps=fps=1/20:start_time=5","-frames:v","3","-y",str(pattern)]
    try:p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=65)
    except subprocess.TimeoutExpired:return []
    if p.returncode!=0:return []
    return sorted(directory.glob("frame-*.png"))[:3]

OCR_VARIANTS={
 "top_left":"crop=iw*0.62:ih*0.30:0:0,scale=2600:-2,format=gray,eq=contrast=1.7:brightness=0.04,unsharp=5:5:1.0",
 "top_left_tight":"crop=iw*0.48:ih*0.22:0:0,scale=2800:-2,format=gray,eq=contrast=1.9:brightness=0.05,unsharp=5:5:1.2",
 "left_bottom":"crop=iw*0.62:ih*0.34:0:ih*0.66,scale=2600:-2,format=gray,eq=contrast=1.7:brightness=0.04,unsharp=5:5:1.0",
 "left_bottom_tight":"crop=iw*0.48:ih*0.24:0:ih*0.76,scale=2800:-2,format=gray,eq=contrast=1.9:brightness=0.05,unsharp=5:5:1.2"
}

def _variant_plan(channel_name):
    n=(channel_name or "").casefold().replace("ё","е")
    if "ditv" in n:
        return ("left_bottom_tight","left_bottom","top_left_tight")
    return ("top_left_tight","top_left","left_bottom_tight")


def _preprocess(frame,out,flt):
    try:p=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",str(frame),"-frames:v","1","-vf",flt,"-y",str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    except subprocess.TimeoutExpired:return False
    return p.returncode==0 and out.exists() and out.stat().st_size>0

def _get_paddle():
    global _PADDLE,_PADDLE_ERROR
    if _PADDLE is not None or _PADDLE_ERROR is not None:
        return _PADDLE
    with _PADDLE_INIT_LOCK:
        if _PADDLE is not None or _PADDLE_ERROR is not None:
            return _PADDLE
        try:
            from paddleocr import PaddleOCR
            try:
                _PADDLE=PaddleOCR(
                    lang="ru",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except TypeError:
                _PADDLE=PaddleOCR(lang="ru",use_angle_cls=False,show_log=False)
        except Exception as exc:
            _PADDLE_ERROR=f"{type(exc).__name__}: {exc}"[:300]
    return _PADDLE

def _extract_strings(obj,out):
    if obj is None:return
    if isinstance(obj,str):
        out.append(obj);return
    if isinstance(obj,dict):
        # PaddleOCR 3.x result dictionaries commonly expose rec_texts.
        # Once recognized text is present, do not recursively walk the same
        # result tree and duplicate those strings.
        rec=obj.get("rec_texts")
        if isinstance(rec,list):
            out.extend(str(x) for x in rec)
            return
        if isinstance(obj.get("text"),str):
            out.append(obj["text"])
            return
        for v in obj.values():
            _extract_strings(v,out)
        return
    if isinstance(obj,(list,tuple)):
        # Legacy shape: [box, (text, score)]
        if len(obj)>=2 and isinstance(obj[1],(list,tuple)) and obj[1] and isinstance(obj[1][0],str):
            out.append(obj[1][0]);return
        for x in obj:_extract_strings(x,out)
        return
    # PaddleOCR 3.x result objects can often be converted to dict/json.
    for attr in ("json","to_dict","dict"):
        try:
            value=getattr(obj,attr)
            value=value() if callable(value) else value
            _extract_strings(value,out)
            return
        except Exception:
            pass

def _paddle_ocr(path):
    engine=_get_paddle()
    if engine is None:return []
    try:
        # One shared model avoids loading 4 copies into RAM. PaddleOCR inference
        # is protected because thread-safety is not part of its public contract.
        with _PADDLE_RUN_LOCK:
            if hasattr(engine,"predict"):
                result=engine.predict(str(path))
            else:
                result=engine.ocr(str(path),cls=False)
        raw=[];_extract_strings(result,raw)
        return _clean_lines(raw)
    except Exception:
        return []

def _tesseract(path,psm):
    try:p=subprocess.run(["tesseract",str(path),"stdout","-l",OCR_LANG,"--psm",str(psm)],capture_output=True,text=True,timeout=10)
    except subprocess.TimeoutExpired:return []
    return _clean_lines(p.stdout.splitlines()) if p.returncode==0 else []

def _ocr_frame(frame,workdir,channel_name="",profile=None):
    lines=[];candidates=[];processed={}
    profile=profile or {}
    primary_tight,primary_wide,opposite_tight=_variant_plan(channel_name)
    learned=profile.get("preferred_zone")
    if learned in OCR_VARIANTS:
        # Start exactly where this channel succeeded previously.
        if learned.startswith("left_bottom"):
            primary_tight,primary_wide,opposite_tight=("left_bottom_tight","left_bottom","top_left_tight")
        elif learned.startswith("top_left"):
            primary_tight,primary_wide,opposite_tight=("top_left_tight","top_left","left_bottom_tight")

    def make(variant):
        if variant in processed:return processed[variant]
        out=workdir/f"{frame.stem}-{variant}.png"
        processed[variant]=out if _preprocess(frame,out,OCR_VARIANTS[variant]) else None
        return processed[variant]

    def add(engine,variant,found,psm=None):
        if not found:return False
        item={"engine":engine,"variant":variant,"lines":found}
        if psm is not None:item["psm"]=psm
        candidates.append(item)
        for x in found:
            if x not in lines:lines.append(x)
        return True

    img=make(primary_tight)
    if img and add("paddleocr",primary_tight,_paddle_ocr(img)):
        return lines,candidates

    img2=make(primary_wide)
    if img2 and add("paddleocr",primary_wide,_paddle_ocr(img2)):
        return lines,candidates

    best=img or img2
    best_variant=primary_tight if img else primary_wide
    if best:
        if add("tesseract",best_variant,_tesseract(best,11),11):
            return lines,candidates
        if add("tesseract",best_variant,_tesseract(best,6),6):
            return lines,candidates

    other=make(opposite_tight)
    if other:
        if add("paddleocr",opposite_tight,_paddle_ocr(other)):
            return lines,candidates
        add("tesseract",opposite_tight,_tesseract(other,11),11)
    return lines,candidates

def _stable_ocr_lines(frames):
    counts=Counter();original={}
    for frame in frames:
        seen=set()
        for line in frame.get("ocr_lines",[]):
            key=_norm(line)
            if not key or key in seen:continue
            seen.add(key);counts[key]+=1;original.setdefault(key,line)
    return [original[k] for k,n in counts.items() if n>=2]


def _load_profiles(path=PROFILES):
    if not path.exists():
        return {}
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data,dict) else {}


def _save_profiles(profiles,path=PROFILES):
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(profiles,ensure_ascii=False,indent=2),
        encoding="utf-8",
    )


def _tokens(value):
    return {x for x in _norm(value).split() if len(x)>=2}


def _is_channel_identity(line,channel_name,provider_name=""):
    """Reject channel/logo text while keeping unrelated movie titles."""
    ln=_norm(line)
    if not ln:
        return True
    names=[_norm(channel_name),_norm(provider_name)]
    for name in names:
        if not name:
            continue
        if ln==name or ln in name or name in ln:
            return True
        lt=_tokens(ln); nt=_tokens(name)
        if lt and nt and len(lt & nt)/max(1,min(len(lt),len(nt)))>=0.8:
            return True
    return False


def _candidate_score(line,engine,variant,profile):
    """Simple ranking, intentionally explainable."""
    text=str(line or "").strip()
    n=_norm(text)
    if not n:
        return -999
    letters=sum(c.isalpha() for c in text)
    if letters<3:
        return -999

    score=0.0
    # Film titles are usually short enough to be a title, not a paragraph.
    score += min(20,letters)/4
    if 3<=len(text)<=60:
        score += 4
    if any("а"<=c.casefold()<="я" or c.casefold()=="ё" for c in text):
        score += 2

    if variant==profile.get("preferred_zone"):
        score += 5
    if engine==profile.get("preferred_engine"):
        score += 4

    # Stable text already learned to be channel decoration is strongly rejected.
    static={_norm(x) for x in profile.get("static_text",[]) if _norm(x)}
    if n in static:
        return -999
    return score


def _pick_title(candidates,channel_name,provider_name,profile):
    ranked=[]
    for item in candidates:
        engine=item.get("engine","")
        variant=item.get("variant","")
        for line in item.get("lines",[]) or []:
            if _is_channel_identity(line,channel_name,provider_name):
                continue
            score=_candidate_score(line,engine,variant,profile)
            if score>-100:
                ranked.append((score,line,engine,variant))
    if not ranked:
        return None
    ranked.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
    score,line,engine,variant=ranked[0]
    return {
        "title":line,
        "score":round(score,2),
        "engine":engine,
        "zone":variant,
    }


def _update_profile(profile,chosen,all_candidates,channel_name,provider_name):
    """Learn successful zone/engine and channel-static text.

    A line is promoted to static_text only after it has co-occurred with at
    least 3 DIFFERENT chosen movie titles. That avoids treating a long movie
    title as a permanent logo just because it survived several hourly runs.
    """
    profile.setdefault("preferred_zone","")
    profile.setdefault("preferred_engine","")
    profile.setdefault("static_text",[])
    profile.setdefault("line_contexts",{})
    profile.setdefault("title_history",[])

    if chosen:
        title=chosen["title"]
        profile["last_title"]=title
        profile["preferred_zone"]=chosen["zone"]
        profile["preferred_engine"]=chosen["engine"]

        hist=profile["title_history"]
        if not hist or _norm(hist[-1])!=_norm(title):
            hist.append(title)
            del hist[:-12]

        chosen_norm=_norm(title)
        for item in all_candidates:
            for line in item.get("lines",[]) or []:
                ln=_norm(line)
                if not ln or ln==chosen_norm:
                    continue
                if _is_channel_identity(line,channel_name,provider_name):
                    if line not in profile["static_text"]:
                        profile["static_text"].append(line)
                    continue
                ctx=profile["line_contexts"].setdefault(ln,[])
                if chosen_norm not in ctx:
                    ctx.append(chosen_norm)
                    del ctx[:-8]
                if len(set(ctx))>=3 and line not in profile["static_text"]:
                    profile["static_text"].append(line)

    profile["updated_at"]=datetime.now(timezone.utc).isoformat()
    profile["static_text"]=profile["static_text"][-30:]
    return profile

def _probe(channel,gap,profile):
    meta=_ffprobe(channel["url"])
    frames=[];all_lines=[];all_candidates=[]
    provider_name=gap.get("provider_name") or channel.get("name","")
    display_name=gap.get("playlist_name") or channel.get("name","")
    with tempfile.TemporaryDirectory(prefix="gap-live-") as td:
        td=Path(td)
        captured=_capture_frames(channel["url"],td)
        for i,fp in enumerate(captured):
            ocr,candidates=_ocr_frame(fp,td,provider_name,profile)
            all_candidates.extend(candidates)
            frames.append({
                "approx_second":FRAME_SECONDS[i],
                "captured":True,
                "sha256":hashlib.sha256(fp.read_bytes()).hexdigest(),
                "ocr_lines":ocr,
                "ocr_candidates":candidates,
            })
            for line in ocr:
                if line not in all_lines:
                    all_lines.append(line)
        while len(frames)<3:
            frames.append({
                "approx_second":FRAME_SECONDS[len(frames)],
                "captured":False,
            })

    chosen=_pick_title(all_candidates,display_name,provider_name,profile)
    _update_profile(profile,chosen,all_candidates,display_name,provider_name)

    return {
        "group":gap.get("group",""),
        "playlist_name":display_name,
        "provider_name":provider_name,
        "provider_tvg_id":gap.get("provider_tvg_id",""),
        "gap_status":gap.get("status",""),
        "found_in_playlist":True,
        "live_playlist_name":channel["name"],
        "live_tvg_id":channel["tvg_id"],
        "stream_metadata":meta,
        "recognized_title":chosen,
        "profile_used":{
            "preferred_zone":profile.get("preferred_zone",""),
            "preferred_engine":profile.get("preferred_engine",""),
            "static_text":profile.get("static_text",[]),
            "last_title":profile.get("last_title",""),
        },
        "ocr_lines":all_lines,
        "stable_ocr_lines":_stable_ocr_lines(frames),
        "unique_frame_hashes":len({f.get("sha256") for f in frames if f.get("sha256")}),
        "captured_frames":sum(1 for x in frames if x.get("captured")),
        "frames":frames,
    }

def main():
    playlist_url=os.environ.get("PLAYLIST_URL","").strip()
    if not playlist_url:raise SystemExit("PLAYLIST_URL missing")
    # Initialize Paddle once before worker threads.
    _get_paddle()
    gaps=_load_gaps()
    if MAX_CHANNELS:gaps=gaps[:MAX_CHANNELS]
    playlist=_parse_m3u(_download_playlist(playlist_url));results={};jobs={};profiles=_load_profiles()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for gap in gaps:
            display=(gap.get("playlist_name") or "").strip()
            provider_name=(gap.get("provider_name") or display).strip()
            key=display or provider_name
            if key in results or key in jobs.values():key=f"{gap.get('group','')}::{key}"
            ch=_find_exact(playlist,provider_name)
            if ch is None:
                results[key]={"group":gap.get("group",""),"playlist_name":display,"provider_name":provider_name,"provider_tvg_id":gap.get("provider_tvg_id",""),"gap_status":gap.get("status",""),"found_in_playlist":False};continue
            profile_key=provider_name or display
            profile=profiles.setdefault(profile_key,{})
            jobs[pool.submit(_probe,ch,gap,profile)]=(key,profile_key)
        for future in as_completed(jobs):
            key,profile_key=jobs[future]
            try:
                results[key]=future.result()
            except Exception as exc:
                results[key]={"playlist_name":key,"found_in_playlist":True,"error":type(exc).__name__}
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"source_gap_file":"output/movie-epg-gaps.csv","target_groups":sorted(TARGET_GROUPS),"channels_considered":len(gaps),"method":"adaptive OCR with persistent per-channel zone/engine/static-text learning","privacy":"stream URLs and video frames are never persisted","frame_seconds":list(FRAME_SECONDS),"ocr_variants":list(OCR_VARIANTS),"paddle_available":_PADDLE is not None,"paddle_error":_PADDLE_ERROR,"channels":results}
    OUTPUT.mkdir(exist_ok=True);_save_profiles(profiles);RESULT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0

if __name__=="__main__":raise SystemExit(main())
