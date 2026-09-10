from pathlib import Path

probe = Path("src/movie_gap_live_probe.py")
workflow = Path(".github/workflows/verify-movie-gaps.yml")

s = probe.read_text(encoding="utf-8")
s = s.replace('FRAME_SECONDS=(4,10)', 'FRAME_SECONDS=(2,8)')
s = s.replace(
    'MAX_WORKERS=max(1,min(8,int(os.environ.get("GAP_PROBE_WORKERS","6"))))',
    'MAX_WORKERS=max(1,min(10,int(os.environ.get("GAP_PROBE_WORKERS","8"))))'
)

start = s.index('def _ocr_frame(')
end = s.index('\\ndef _stable_ocr_lines', start)
new_ocr = '''def _ocr_frame(frame,workdir,channel_name="",profile=None,provider_name=""):
    # Fast path first: learned zone + Tesseract. Paddle is fallback only.
    lines=[];candidates=[];processed={}
    profile=profile or {}
    learned=profile.get("preferred_zone","")

    if learned in OCR_VARIANTS:
        plan=[learned]
        if learned.startswith("top"):
            plan += ["top_left_tight","top_left","top_band","left_bottom_tight","bottom_band"]
        else:
            plan += ["left_bottom_tight","left_bottom","bottom_band","top_left_tight","top_band"]
    else:
        primary_tight,primary_wide,opposite_tight=_variant_plan(channel_name)
        plan=[primary_tight,primary_wide,opposite_tight,"top_band","bottom_band"]

    plan=list(dict.fromkeys(x for x in plan if x in OCR_VARIANTS))

    def make(variant):
        if variant in processed:return processed[variant]
        out=workdir/f"{frame.stem}-{variant}.png"
        processed[variant]=out if _preprocess(frame,out,OCR_VARIANTS[variant]) else None
        return processed[variant]

    def add(engine,variant,found,psm=None):
        if not found:return
        item={"engine":engine,"variant":variant,"lines":found}
        if psm is not None:item["psm"]=psm
        candidates.append(item)
        for x in found:
            if x not in lines:lines.append(x)

    for variant in plan:
        img=make(variant)
        if not img:continue
        add("tesseract",variant,_tesseract(img,11),11)
        chosen=_pick_title(candidates,channel_name,provider_name,profile)
        if chosen and chosen.get("confidence")=="high":
            return lines,candidates
        add("tesseract",variant,_tesseract(img,6),6)
        chosen=_pick_title(candidates,channel_name,provider_name,profile)
        if chosen and chosen.get("confidence")=="high":
            return lines,candidates

    for variant in plan:
        img=make(variant)
        if not img:continue
        add("paddleocr",variant,_paddle_ocr(img))
        chosen=_pick_title(candidates,channel_name,provider_name,profile)
        if chosen and chosen.get("confidence")=="high":
            break

    return lines,candidates
'''
s = s[:start] + new_ocr + s[end:]

old = 'def _probe(channel,gap,profile):\\n    meta=_ffprobe(channel["url"])\\n    frames=[];all_lines=[];all_candidates=[];chosen=None'
new = 'def _probe(channel,gap,profile):\\n    meta={"ok":None,"skipped":"title-first"}\\n    frames=[];all_lines=[];all_candidates=[];chosen=None'
if old not in s:
    raise SystemExit("expected _probe header not found")
s = s.replace(old, new, 1)

needle = '    if chosen is None or chosen.get("confidence")!="high":\\n        chosen=_pick_title(all_candidates,display_name,provider_name,profile)\\n    _update_profile(profile,chosen,all_candidates,display_name,provider_name)\\n'
replacement = '    if chosen is None or chosen.get("confidence")!="high":\\n        chosen=_pick_title(all_candidates,display_name,provider_name,profile)\\n    if chosen is None or chosen.get("confidence")!="high":\\n        meta=_ffprobe(channel["url"])\\n    _update_profile(profile,chosen,all_candidates,display_name,provider_name)\\n'
if needle not in s:
    raise SystemExit("expected post-OCR block not found")
s = s.replace(needle, replacement, 1)

s = s.replace('    # Initialize Paddle once before worker threads.\\n    _get_paddle()\\n', '    # Paddle initializes lazily only after Tesseract fast path fails.\\n')
s = s.replace(
    '"method":"learned-zone-first OCR with full-width top/bottom fallback; second frame only when needed"',
    '"method":"hourly title-first recovery: learned-zone Tesseract fast path, Paddle and ffprobe only on failure"'
)
probe.write_text(s, encoding="utf-8")

w = workflow.read_text(encoding="utf-8")
w = w.replace('cancel-in-progress: false', 'cancel-in-progress: true')
w = w.replace('GAP_PROBE_WORKERS: "6"', 'GAP_PROBE_WORKERS: "8"')
workflow.write_text(w, encoding="utf-8")

print("changed:", probe)
print("changed:", workflow)
