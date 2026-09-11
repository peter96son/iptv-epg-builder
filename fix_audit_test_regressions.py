#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path.cwd()

def rd(rel):
    p = ROOT / rel
    if not p.exists():
        raise SystemExit(f"missing: {rel}")
    return p.read_text(encoding="utf-8")

def wr(rel, s):
    (ROOT / rel).write_text(s, encoding="utf-8")

# Update + metadata backfill MUST serialize against each other.
for rel in [".github/workflows/update.yml", ".github/workflows/backfill-metadata.yml"]:
    s = rd(rel)
    s = s.replace("  group: epg-update\n", "  group: epg-metadata\n")
    s = s.replace("  group: metadata-backfill\n", "  group: epg-metadata\n")
    wr(rel, s)

# Movie jobs stay isolated from metadata jobs.
gap = rd(".github/workflows/verify-movie-gaps.yml")
if "  group: epg-metadata\n" in gap:
    gap = gap.replace("  group: epg-metadata\n", "  group: movie-gap-recovery\n", 1)
wr(".github/workflows/verify-movie-gaps.yml", gap)

existing = rd(".github/workflows/verify-existing-movie-epg.yml")
if "  group: epg-metadata\n" in existing:
    existing = existing.replace("  group: epg-metadata\n", "  group: movie-existing-verifier\n", 1)
wr(".github/workflows/verify-existing-movie-epg.yml", existing)

# Critical runtime fixes.
p = "src/movie_gap_live_probe.py"
s = rd(p)
s = s.replace(
    "    # Initialize Paddle once before worker threads.\n    _get_paddle()\n",
    "    # Paddle is expensive; initialize it only when explicitly enabled.\n"
    "    if USE_PADDLE:\n"
    "        _get_paddle()\n",
)

old = 'def _probe(channel,gap,profile):\n    meta=_ffprobe(channel["url"])\n    frames=[];all_lines=[];all_candidates=[];chosen=None\n'
new = 'def _probe(channel,gap,profile):\n    meta=None\n    frames=[];all_lines=[];all_candidates=[];chosen=None\n'
if old in s:
    s = s.replace(old, new, 1)

old = '''    if chosen is None or chosen.get("confidence")!="high":
        chosen=_pick_title(all_candidates,display_name,provider_name,profile)
    _update_profile(profile,chosen,all_candidates,display_name,provider_name)

    return {
'''
new = '''    if chosen is None or chosen.get("confidence")!="high":
        chosen=_pick_title(all_candidates,display_name,provider_name,profile)

    if not chosen or chosen.get("confidence")!="high":
        meta=_ffprobe(channel["url"])
    else:
        meta={"ok":True,"skipped":"high-confidence-ocr"}

    _update_profile(profile,chosen,all_candidates,display_name,provider_name)

    return {
'''
if old not in s:
    raise SystemExit("cannot patch ffprobe ordering")
s = s.replace(old, new, 1)
wr(p, s)

# Stale cache test -> current durability contract.
p = "tests/test_metadata_performance_v111.py"
s = rd(p)
s = s.replace(
    '    assert "actions/cache/restore@v4" in workflow\n',
    '    assert "epg-cache-${{ runner.os }}-${{ github.run_id }}" not in workflow\n'
    '    assert "python -m src.metadata_snapshot restore" in workflow\n'
)
wr(p, s)

# OCR tests -> current adaptive fast contract.
p = "tests/test_v155_movie_gap_live_probe.py"
s = rd(p)

start = s.find("def test_capture_is_single_connection_with_spaced_frames():")
if start != -1:
    nxt = s.find("\ndef ", start + 5)
    if nxt == -1:
        nxt = len(s)
    replacement = '''def test_capture_is_adaptive_and_second_frame_is_optional():
    source=inspect.getsource(m._probe)
    assert "_capture_frame(" in source
    assert "break" in source

'''
    s = s[:start] + replacement + s[nxt+1:]

s = s.replace("    assert m.MAX_WORKERS==4\n", "    assert m.MAX_WORKERS==8\n")

old = '''def test_paddle_and_corner_ocr_are_enabled():
    assert "top_left" in m.OCR_VARIANTS
    assert "left_bottom" in m.OCR_VARIANTS
    source=inspect.getsource(m._ocr_frame)
    assert "_paddle_ocr(img)" in source
    assert "_tesseract(best,11)" in source
'''
new = '''def test_tesseract_first_and_optional_paddle_fallback():
    assert "top_left" in m.OCR_VARIANTS
    assert "left_bottom" in m.OCR_VARIANTS
    source=inspect.getsource(m._ocr_frame)
    assert "_tesseract(img,11)" in source
    assert "_tesseract(img,6)" in source
    assert "if USE_PADDLE:" in source
    assert "_paddle_ocr(img)" in source
'''
if old in s:
    s = s.replace(old, new, 1)
else:
    st = s.find("def test_paddle_and_corner_ocr_are_enabled():")
    if st != -1:
        nx = s.find("\ndef ", st + 5)
        if nx == -1:
            nx = len(s)
        s = s[:st] + new + "\n" + s[nx+1:]

if "test_ffprobe_is_not_on_high_confidence_ocr_path" not in s:
    s += '''

def test_ffprobe_is_not_on_high_confidence_ocr_path():
    source=inspect.getsource(m._probe)
    assert 'skipped":"high-confidence-ocr"' in source
    assert 'meta=_ffprobe(channel["url"])' in source
'''
wr(p, s)

p = "tests/test_v159_paddleocr.py"
s = rd(p)
s = s.replace("    assert m.FRAME_SECONDS==(5,25,45)\n",
              "    assert m.FRAME_SECONDS==(2,8)\n")
if "test_paddle_disabled_does_not_initialize_in_main" not in s:
    s += '''

def test_paddle_disabled_does_not_initialize_in_main():
    import inspect
    source=inspect.getsource(m.main)
    assert "if USE_PADDLE:" in source
    assert "_get_paddle()" in source
'''
wr(p, s)

# Final static audit.
errors = []
u = rd(".github/workflows/update.yml")
b = rd(".github/workflows/backfill-metadata.yml")
g = rd(".github/workflows/verify-movie-gaps.yml")
e = rd(".github/workflows/verify-existing-movie-epg.yml")
probe = rd("src/movie_gap_live_probe.py")
run = rd("run.py")

if "group: epg-metadata" not in u or "group: epg-metadata" not in b:
    errors.append("update/backfill are not serialized")
if "group: movie-gap-recovery" not in g:
    errors.append("gap workflow not isolated")
if "group: movie-existing-verifier" not in e:
    errors.append("existing verifier not isolated")
if "epg-cache-${{ runner.os }}-${{ github.run_id }}" in u+b+g+e:
    errors.append("run-id giant cache still present")
if "live_ocr_epg_overlay" in e or "apply_live_ocr_epg_overlay" in run:
    errors.append("synthetic OCR mutation still active")
if "output/epg.xml.gz" in e:
    errors.append("existing verifier still publishes EPG")
if "if USE_PADDLE:" not in probe:
    errors.append("Paddle gate missing")
if 'meta={"ok":True,"skipped":"high-confidence-ocr"}' not in probe:
    errors.append("ffprobe fast-path skip missing")

if errors:
    print("AUDIT FAILED")
    for x in errors:
        print(" -", x)
    sys.exit(1)

print("AUDIT OK")
print("Corrected metadata serialization and current tests/runtime guards.")
