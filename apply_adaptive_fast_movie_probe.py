from pathlib import Path

p = Path("src/movie_gap_live_probe.py")
s = p.read_text(encoding="utf-8")

def rep(old, new):
    global s
    if old not in s:
        raise SystemExit("STOP: expected block not found; repo differs from expected main")
    s = s.replace(old, new, 1)

rep('FRAME_SECONDS=(5,25,45)\n','FRAME_SECONDS=(4,10)\n')
rep('MAX_WORKERS=max(1,min(4,int(os.environ.get("GAP_PROBE_WORKERS","4"))))\n',
    'MAX_WORKERS=max(1,min(8,int(os.environ.get("GAP_PROBE_WORKERS","6"))))\n')

old_capture = '''def _capture_frames(url,directory):
    pattern=directory/"frame-%02d.png"
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-rw_timeout","10000000","-i",url,"-t","49","-vf","fps=fps=1/20:start_time=5","-frames:v","3","-y",str(pattern)]
    try:p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=65)
    except subprocess.TimeoutExpired:return []
    if p.returncode!=0:return []
    return sorted(directory.glob("frame-*.png"))[:3]
'''
new_capture = '''def _capture_frame(url,directory,second,index):
    out=directory/f"frame-{index:02d}.png"
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-rw_timeout","8000000","-i",url,"-ss",str(second),"-frames:v","1","-y",str(out)]
    try:p=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=max(18,second+12))
    except subprocess.TimeoutExpired:return None
    return out if p.returncode==0 and out.exists() and out.stat().st_size>0 else None
'''
rep(old_capture,new_capture)

old_probe = '''def _probe(channel,gap,profile):
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
'''
new_probe = '''def _probe(channel,gap,profile):
    meta=_ffprobe(channel["url"])
    frames=[];all_lines=[];all_candidates=[];chosen=None
    provider_name=gap.get("provider_name") or channel.get("name","")
    display_name=gap.get("playlist_name") or channel.get("name","")
    with tempfile.TemporaryDirectory(prefix="gap-live-") as td:
        td=Path(td)
        for i,second in enumerate(FRAME_SECONDS):
            fp=_capture_frame(channel["url"],td,second,i+1)
            if fp is None:
                frames.append({"approx_second":second,"captured":False})
                continue
            ocr,candidates=_ocr_frame(fp,td,provider_name,profile)
            all_candidates.extend(candidates)
            frames.append({
                "approx_second":second,
                "captured":True,
                "sha256":hashlib.sha256(fp.read_bytes()).hexdigest(),
                "ocr_lines":ocr,
                "ocr_candidates":candidates,
            })
            for line in ocr:
                if line not in all_lines:
                    all_lines.append(line)
            chosen=_pick_title(all_candidates,display_name,provider_name,profile)
            if chosen and chosen.get("confidence")=="high":
                break
        while len(frames)<len(FRAME_SECONDS):
            frames.append({
                "approx_second":FRAME_SECONDS[len(frames)],
                "captured":False,
                "skipped_after_high_confidence":True,
            })

    if chosen is None or chosen.get("confidence")!="high":
        chosen=_pick_title(all_candidates,display_name,provider_name,profile)
    _update_profile(profile,chosen,all_candidates,display_name,provider_name)
'''
rep(old_probe,new_probe)

rep('"method":"adaptive OCR with persistent per-channel zone/engine/static-text learning"',
    '"method":"one-frame-first adaptive OCR; second frame only when first is not high-confidence"')

p.write_text(s,encoding="utf-8")
print("changed: src/movie_gap_live_probe.py")

p=Path(".github/workflows/verify-movie-gaps.yml")
s=p.read_text(encoding="utf-8")
old='          GAP_PROBE_WORKERS: "4"\n'
new='          GAP_PROBE_WORKERS: "6"\n'
if old not in s:
    raise SystemExit("STOP: GAP_PROBE_WORKERS setting not found")
p.write_text(s.replace(old,new,1),encoding="utf-8")
print("changed: .github/workflows/verify-movie-gaps.yml")
print("OK")
