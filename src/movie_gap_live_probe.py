from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"output"

TARGET_GROUPS={"Кино","USSR","Кинозалы","Кино 4K"}
GAPS=OUTPUT/"movie-epg-gaps.csv"
RESULT=OUTPUT/"movie-gap-live-probe.json"

FRAME_SECONDS=(4,10,16)
OCR_LANG=os.environ.get("STREAM_OCR_LANG","rus+eng")
MAX_CHANNELS=max(0,int(os.environ.get("GAP_PROBE_MAX_CHANNELS","0")))
MAX_WORKERS=max(1,min(4,int(os.environ.get("GAP_PROBE_WORKERS","4"))))


def _download_playlist(url:str)->str:
    req=Request(url,headers={"User-Agent":"IPTV-EPG-Builder gap verifier"})
    with urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","replace")


def _parse_m3u(text:str)->list[dict]:
    rows=[]; info=None
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith("#EXTINF:"):
            attrs=dict(re.findall(r'([\w-]+)="([^"]*)"',line))
            info={
                "name":line.rsplit(",",1)[-1].strip(),
                "tvg_id":attrs.get("tvg-id",""),
                "group":attrs.get("group-title",""),
            }
        elif info and line and not line.startswith("#"):
            row=dict(info); row["url"]=line; rows.append(row); info=None
    return rows


def _load_gaps(path:Path=GAPS)->list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    return [
        r for r in rows
        if (r.get("group") or "").strip() in TARGET_GROUPS
        and (r.get("status") or "").strip()
        and (r.get("status") or "").strip() != "OK"
    ]


def _norm(value:str)->str:
    s=(value or "").casefold().replace("ё","е")
    s=re.sub(r"\b(?:fhd|uhd|4k|hd|sd|hevc|h265|h\.265)\b"," ",s)
    s=re.sub(r"[^a-zа-я0-9]+"," ",s)
    return " ".join(s.split())


def _find_exact(rows:list[dict],name:str)->dict|None:
    # First use the exact provider name. Only use normalized matching when it is
    # unique, so VHS HD can never silently become BCU VHS HD.
    exact=[r for r in rows if r["name"]==name]
    if len(exact)==1:
        return exact[0]
    n=_norm(name)
    normalized=[r for r in rows if _norm(r["name"])==n]
    return normalized[0] if len(normalized)==1 else None


def _clean_ocr(text:str)->list[str]:
    out=[]
    for raw in (text or "").splitlines():
        line=re.sub(r"\s+"," ",raw).strip(" |_-—–")
        if len(line)<3:
            continue
        if sum(ch.isalnum() for ch in line)<max(2,len(line)//4):
            continue
        if line not in out:
            out.append(line)
    return out



def _redact_metadata(value:str)->str:
    value=str(value or "")
    value=re.sub(r"https?://\S+","[URL]",value,flags=re.I)
    return value[:1000]

def _ffprobe(url:str)->dict:
    cmd=[
        "ffprobe","-v","error","-rw_timeout","10000000",
        "-analyzeduration","6000000","-probesize","6000000",
        "-show_format","-show_programs","-show_streams","-of","json",url,
    ]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=12)
    except subprocess.TimeoutExpired:
        return {"ok":False,"error":"timeout"}
    if p.returncode:
        return {"ok":False,"error":"probe-failed"}
    try:
        data=json.loads(p.stdout)
    except Exception:
        return {"ok":False,"error":"invalid-json"}
    tags={}
    wanted={"title","service_name","service_provider","icy-title","icy-name","artist","album","description","comment"}
    def add(obj,prefix):
        for k,v in (obj.get("tags") or {}).items():
            if k.casefold() in wanted:
                tags[f"{prefix}.{k}"]=_redact_metadata(v)
    add(data.get("format") or {},"format")
    for i,x in enumerate(data.get("programs") or []): add(x,f"program[{i}]")
    for i,x in enumerate(data.get("streams") or []): add(x,f"stream[{i}]")
    return {"ok":True,"metadata":tags}


def _capture_frames(url:str,directory:Path)->list[Path]:
    """Capture 3 lower-screen frames from one live connection."""
    pattern=directory/"frame-%02d.png"
    vf="fps=fps=1/6:start_time=4,crop=iw:ih*0.48:0:ih*0.52,scale=1600:-2"
    cmd=[
        "ffmpeg","-hide_banner","-loglevel","error",
        "-rw_timeout","10000000",
        "-i",url,
        "-t","20",
        "-vf",vf,
        "-frames:v","3",
        "-y",str(pattern),
    ]
    try:
        proc=subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=34,
        )
    except subprocess.TimeoutExpired:
        return []
    if proc.returncode!=0:
        return []
    return sorted(directory.glob("frame-*.png"))[:3]

def _ocr(path:Path)->list[str]:
    try:
        p=subprocess.run(
            ["tesseract",str(path),"stdout","-l",OCR_LANG,"--psm","6"],
            capture_output=True,text=True,timeout=8,
        )
    except subprocess.TimeoutExpired:
        return []
    return _clean_ocr(p.stdout) if p.returncode==0 else []


def _probe(channel:dict,gap:dict)->dict:
    # URL stays local to this function and is never written to output.
    meta=_ffprobe(channel["url"])
    frames=[]; lines=[]
    with tempfile.TemporaryDirectory(prefix="gap-live-") as td:
        td=Path(td)
        captured=_capture_frames(channel["url"],td)
        approx_seconds=FRAME_SECONDS
        for i,fp in enumerate(captured):
            ocr=_ocr(fp)
            frames.append({
                "approx_second":approx_seconds[i] if i<len(approx_seconds) else None,
                "captured":True,
                "sha256":hashlib.sha256(fp.read_bytes()).hexdigest(),
                "ocr_lines":ocr,
            })
            for line in ocr:
                if line not in lines:
                    lines.append(line)
        while len(frames)<3:
            frames.append({
                "approx_second":approx_seconds[len(frames)],
                "captured":False,
            })
    return {
        "group":gap.get("group",""),
        "playlist_name":gap.get("playlist_name",""),
        "provider_name":gap.get("provider_name",""),
        "provider_tvg_id":gap.get("provider_tvg_id",""),
        "gap_status":gap.get("status",""),
        "found_in_playlist":True,
        "live_playlist_name":channel["name"],
        "live_tvg_id":channel["tvg_id"],
        "stream_metadata":meta,
        "ocr_lines":lines,
        "captured_frames":sum(1 for x in frames if x.get("captured")),
        "frames":frames,
    }


def main()->int:
    playlist_url=os.environ.get("PLAYLIST_URL","").strip()
    if not playlist_url:
        raise SystemExit("PLAYLIST_URL missing")

    gaps=_load_gaps()
    if MAX_CHANNELS:
        gaps=gaps[:MAX_CHANNELS]
    playlist=_parse_m3u(_download_playlist(playlist_url))
    results={}
    jobs={}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for gap in gaps:
            display_name=(gap.get("playlist_name") or "").strip()
            provider_name=(gap.get("provider_name") or display_name).strip()
            base_key=display_name or provider_name
            result_key=base_key
            if result_key in results or result_key in jobs.values():
                result_key=f"{gap.get('group','')}::{base_key}"
            ch=_find_exact(playlist,provider_name)
            if ch is None:
                results[result_key]={
                    "group":gap.get("group",""),
                    "playlist_name":display_name,
                    "provider_name":provider_name,
                    "provider_tvg_id":gap.get("provider_tvg_id",""),
                    "gap_status":gap.get("status",""),
                    "found_in_playlist":False,
                }
                continue
            jobs[pool.submit(_probe,ch,gap)]=result_key

        for future in as_completed(jobs):
            name=jobs[future]
            try:
                results[name]=future.result()
            except Exception as exc:
                results[name]={
                    "playlist_name":name,
                    "found_in_playlist":True,
                    "error":type(exc).__name__,
                }

    payload={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "source_gap_file":"output/movie-epg-gaps.csv",
        "target_groups":sorted(TARGET_GROUPS),
        "channels_considered":len(gaps),
        "method":"live ffprobe metadata + temporary lower-screen OCR",
        "privacy":"stream URLs and video frames are never persisted",
        "channels":results,
    }
    OUTPUT.mkdir(exist_ok=True)
    RESULT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    print(
        f"[gap-live-probe] gaps={len(gaps)} probed={sum(1 for x in results.values() if x.get('found_in_playlist'))}",
        flush=True,
    )
    return 0


if __name__=="__main__":
    raise SystemExit(main())
