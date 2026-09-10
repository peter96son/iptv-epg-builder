from pathlib import Path

p = Path("src/movie_gap_live_probe.py")
s = p.read_text(encoding="utf-8")

old = '''OCR_VARIANTS={
 "top_left":"crop=iw*0.62:ih*0.30:0:0,scale=2600:-2,format=gray,eq=contrast=1.7:brightness=0.04,unsharp=5:5:1.0",
 "top_left_tight":"crop=iw*0.48:ih*0.22:0:0,scale=2800:-2,format=gray,eq=contrast=1.9:brightness=0.05,unsharp=5:5:1.2",
 "left_bottom":"crop=iw*0.62:ih*0.34:0:ih*0.66,scale=2600:-2,format=gray,eq=contrast=1.7:brightness=0.04,unsharp=5:5:1.0",
 "left_bottom_tight":"crop=iw*0.48:ih*0.24:0:ih*0.76,scale=2800:-2,format=gray,eq=contrast=1.9:brightness=0.05,unsharp=5:5:1.2"
}
'''
new = '''OCR_VARIANTS={
 "top_left":"crop=iw*0.62:ih*0.30:0:0,scale=2600:-2,format=gray,eq=contrast=1.7:brightness=0.04,unsharp=5:5:1.0",
 "top_left_tight":"crop=iw*0.48:ih*0.22:0:0,scale=2800:-2,format=gray,eq=contrast=1.9:brightness=0.05,unsharp=5:5:1.2",
 "top_band":"crop=iw:ih*0.30:0:0,scale=2800:-2,format=gray,eq=contrast=1.8:brightness=0.04,unsharp=5:5:1.1",
 "left_bottom":"crop=iw*0.62:ih*0.34:0:ih*0.66,scale=2600:-2,format=gray,eq=contrast=1.7:brightness=0.04,unsharp=5:5:1.0",
 "left_bottom_tight":"crop=iw*0.48:ih*0.24:0:ih*0.76,scale=2800:-2,format=gray,eq=contrast=1.9:brightness=0.05,unsharp=5:5:1.2",
 "bottom_band":"crop=iw:ih*0.30:0:ih*0.70,scale=2800:-2,format=gray,eq=contrast=1.8:brightness=0.04,unsharp=5:5:1.1"
}
'''
assert old in s
s = s.replace(old, new)

start = s.index("def _ocr_frame(")
end = s.index("\ndef _stable_ocr_lines", start)
new_func = '''def _ocr_frame(frame,workdir,channel_name="",profile=None,provider_name=""):
    """Read title text without letting one garbage OCR hit hide better zones.

    The previously successful zone is tried first. A zone is remembered only
    when a plausible movie title is selected; otherwise the scan expands to
    full-width top/bottom bands.
    """
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
        if not img:
            continue

        add("paddleocr",variant,_paddle_ocr(img))
        add("tesseract",variant,_tesseract(img,11),11)
        chosen=_pick_title(candidates,channel_name,provider_name,profile)
        if not (chosen and chosen.get("confidence")=="high"):
            add("tesseract",variant,_tesseract(img,6),6)
            chosen=_pick_title(candidates,channel_name,provider_name,profile)

        if chosen and chosen.get("confidence")=="high":
            break

    return lines,candidates
'''
s = s[:start] + new_func + s[end:]

old_call = 'ocr,candidates=_ocr_frame(fp,td,provider_name,profile)'
new_call = 'ocr,candidates=_ocr_frame(fp,td,display_name,profile,provider_name)'
assert old_call in s
s = s.replace(old_call, new_call)

old_method = '"method":"one-frame-first adaptive OCR; second frame only when first is not high-confidence",'
new_method = '"method":"learned-zone-first OCR with full-width top/bottom fallback; second frame only when needed",'
if old_method in s:
    s = s.replace(old_method, new_method)

p.write_text(s, encoding="utf-8")
print("changed:", p)
