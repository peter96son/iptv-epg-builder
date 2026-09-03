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
 "top_left":"crop=iw*0.62:ih*0.30:0:0,scale=3000:-2,format=gray,eq=contrast=1.8:brightness=0.05,unsharp=5:5:1.2",
 "top_left_tight":"crop=iw*0.48:ih*0.22:0:0,scale=3200:-2,format=gray,eq=contrast=2.0:brightness=0.06,unsharp=5:5:1.4",
 "left_bottom":"crop=iw*0.62:ih*0.34:0:ih*0.66,scale=3000:-2,format=gray,eq=contrast=1.8:brightness=0.05,unsharp=5:5:1.2",
 "left_bottom_tight":"crop=iw*0.48:ih*0.24:0:ih*0.76,scale=3200:-2,format=gray,eq=contrast=2.0:brightness=0.06,unsharp=5:5:1.4",
 "lower50":"crop=iw:ih*0.50:0:ih*0.50,scale=2200:-2,format=gray,eq=contrast=1.45:brightness=0.03,unsharp=5:5:0.8"
}

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

def _ocr_frame(frame,workdir):
    lines=[];candidates=[]
    for variant,flt in OCR_VARIANTS.items():
        processed=workdir/f"{frame.stem}-{variant}.png"
        if not _preprocess(frame,processed,flt):continue

        p_lines=_paddle_ocr(processed)
        if p_lines:candidates.append({"engine":"paddleocr","variant":variant,"lines":p_lines})
        for x in p_lines:
            if x not in lines:lines.append(x)

        # Tesseract is fallback/second opinion, not the primary recognizer.
        for psm in (6,7,11):
            t_lines=_tesseract(processed,psm)
            if t_lines:candidates.append({"engine":"tesseract","variant":variant,"psm":psm,"lines":t_lines})
            for x in t_lines:
                if x not in lines:lines.append(x)
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

def _probe(channel,gap):
    meta=_ffprobe(channel["url"]);frames=[];all_lines=[]
    with tempfile.TemporaryDirectory(prefix="gap-live-") as td:
        td=Path(td);captured=_capture_frames(channel["url"],td)
        for i,fp in enumerate(captured):
            ocr,candidates=_ocr_frame(fp,td)
            frames.append({"approx_second":FRAME_SECONDS[i],"captured":True,"sha256":hashlib.sha256(fp.read_bytes()).hexdigest(),"ocr_lines":ocr,"ocr_candidates":candidates})
            for line in ocr:
                if line not in all_lines:all_lines.append(line)
        while len(frames)<3:frames.append({"approx_second":FRAME_SECONDS[len(frames)],"captured":False})
    return {"group":gap.get("group",""),"playlist_name":gap.get("playlist_name",""),"provider_name":gap.get("provider_name",""),"provider_tvg_id":gap.get("provider_tvg_id",""),"gap_status":gap.get("status",""),"found_in_playlist":True,"live_playlist_name":channel["name"],"live_tvg_id":channel["tvg_id"],"stream_metadata":meta,"ocr_lines":all_lines,"stable_ocr_lines":_stable_ocr_lines(frames),"unique_frame_hashes":len({f.get("sha256") for f in frames if f.get("sha256")}),"captured_frames":sum(1 for x in frames if x.get("captured")),"frames":frames}

def main():
    playlist_url=os.environ.get("PLAYLIST_URL","").strip()
    if not playlist_url:raise SystemExit("PLAYLIST_URL missing")
    # Initialize Paddle once before worker threads.
    _get_paddle()
    gaps=_load_gaps()
    if MAX_CHANNELS:gaps=gaps[:MAX_CHANNELS]
    playlist=_parse_m3u(_download_playlist(playlist_url));results={};jobs={}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for gap in gaps:
            display=(gap.get("playlist_name") or "").strip()
            provider_name=(gap.get("provider_name") or display).strip()
            key=display or provider_name
            if key in results or key in jobs.values():key=f"{gap.get('group','')}::{key}"
            ch=_find_exact(playlist,provider_name)
            if ch is None:
                results[key]={"group":gap.get("group",""),"playlist_name":display,"provider_name":provider_name,"provider_tvg_id":gap.get("provider_tvg_id",""),"gap_status":gap.get("status",""),"found_in_playlist":False};continue
            jobs[pool.submit(_probe,ch,gap)]=key
        for future in as_completed(jobs):
            key=jobs[future]
            try:results[key]=future.result()
            except Exception as exc:results[key]={"playlist_name":key,"found_in_playlist":True,"error":type(exc).__name__}
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"source_gap_file":"output/movie-epg-gaps.csv","target_groups":sorted(TARGET_GROUPS),"channels_considered":len(gaps),"method":"live ffprobe + spaced frames + PaddleOCR primary + Tesseract fallback","privacy":"stream URLs and video frames are never persisted","frame_seconds":list(FRAME_SECONDS),"ocr_variants":list(OCR_VARIANTS),"paddle_available":_PADDLE is not None,"paddle_error":_PADDLE_ERROR,"channels":results}
    OUTPUT.mkdir(exist_ok=True);RESULT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0

if __name__=="__main__":raise SystemExit(main())
