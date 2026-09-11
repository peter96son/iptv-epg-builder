#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path.cwd()
def r(p): return (ROOT/p).read_text(encoding='utf-8')
def w(p,s): (ROOT/p).write_text(s,encoding='utf-8')
def one(s,a,b,label):
    if a not in s: raise SystemExit(f'cannot patch {label}: expected text not found')
    return s.replace(a,b,1)

# workflows
p='.github/workflows/update.yml'; s=r(p); s=one(s,'  group: epg-metadata\n','  group: epg-update\n',p); w(p,s)
p='.github/workflows/backfill-metadata.yml'; s=r(p); s=one(s,'  group: epg-metadata\n','  group: metadata-backfill\n',p); w(p,s)
p='.github/workflows/verify-movie-gaps.yml'; s=r(p); s=one(s,'  group: epg-metadata\n','  group: movie-gap-recovery\n',p)
if 'GAP_PROBE_PADDLE:' not in s: s=one(s,'          GAP_PROBE_WORKERS: "8"\n','          GAP_PROBE_WORKERS: "8"\n          GAP_PROBE_PADDLE: "0"\n',p)
s=s.replace('          EPG_DISCOVERY_TIMEOUT_CAP: "60"\n','          EPG_DISCOVERY_TIMEOUT_CAP: "25"\n          EPG_DISCOVERY_WORKERS: "4"\n')
s=one(s,'''      - name: Judge — select only evidence-matching EPG donors
        env:
          PLAYLIST_URL: ${{ secrets.PLAYLIST_URL }}
        run: python -m src.movie_epg_recovery select
''','''      - name: Judge — select only evidence-matching EPG donors
        env:
          PLAYLIST_URL: ${{ secrets.PLAYLIST_URL }}
          EPG_SOURCE_TIMEOUT_CAP: "25"
          EPG_SOURCE_RETRIES_CAP: "1"
          RESELECT_SKIP_METADATA_ENRICH: "1"
        run: python -m src.movie_epg_recovery select
''',p); w(p,s)

p='.github/workflows/verify-existing-movie-epg.yml'; s=r(p); s=one(s,'  group: epg-metadata\n','  group: movie-existing-verifier\n',p); s=s.replace('  cancel-in-progress: false\n','  cancel-in-progress: true\n',1)
if 'GAP_PROBE_PADDLE:' not in s: s=one(s,'          LIVE_EPG_MISMATCH_CONFIRM: "2"\n','          LIVE_EPG_MISMATCH_CONFIRM: "2"\n          GAP_PROBE_PADDLE: "0"\n',p)
s=s.replace('''      - name: Apply confirmed live mismatches to OCR state
        run: python -m src.live_ocr_epg_overlay

''','')
s=one(s,'          bash .github/scripts/safe-publish.sh "Verify existing movie EPG against live stream"             output/live-epg-verification.json             output/live-epg-verification-state.json             output/live-ocr-epg-state.json             output/epg.xml.gz             output/uhf-mapping.json             data/live_epg_observations_v1518.csv\n','          bash .github/scripts/safe-publish.sh "Verify existing movie EPG against live stream"             output/live-epg-verification.json             output/live-epg-verification-state.json             data/live_epg_observations_v1518.csv\n',p); w(p,s)

# normal build: never reapply synthetic OCR
p='run.py'; s=r(p); s=s.replace('from src.live_ocr_epg_overlay import run as apply_live_ocr_epg_overlay\n',''); s=s.replace('''    ocr_overlay = apply_live_ocr_epg_overlay(consume_probe=False)
    print(
        f"[live-ocr-epg] active={ocr_overlay.get('overlay',{}).get('active',0)}; "
        f"applied={ocr_overlay.get('overlay',{}).get('applied',0)}"
    )
''',''); w(p,s)

# selector: skip full metadata scan only in hourly recovery
p='src/source_reselector.py'; s=r(p)
old='''    # Re-apply local SQLite metadata to newly inserted programmes.
    old_env={k:os.environ.get(k) for k in (
        "METADATA_MAX_TITLES","METADATA_MAX_HTTP_REQUESTS","METADATA_MULTI_FALLBACK"
    )}
    try:
        os.environ["METADATA_MAX_TITLES"]="0"
        os.environ["METADATA_MAX_HTTP_REQUESTS"]="0"
        os.environ["METADATA_MULTI_FALLBACK"]="0"
        enrich_metadata(tv,mapping_rows,ROOT,OUTPUT)
    finally:
        for k,v in old_env.items():
            if v is None:
                os.environ.pop(k,None)
            else:
                os.environ[k]=v

'''
new='''    # Full metadata enrichment belongs to the regular Update EPG run.
    if not _enabled(os.environ.get("RESELECT_SKIP_METADATA_ENRICH", "0")):
        old_env={k:os.environ.get(k) for k in (
            "METADATA_MAX_TITLES","METADATA_MAX_HTTP_REQUESTS","METADATA_MULTI_FALLBACK"
        )}
        try:
            os.environ["METADATA_MAX_TITLES"]="0"
            os.environ["METADATA_MAX_HTTP_REQUESTS"]="0"
            os.environ["METADATA_MULTI_FALLBACK"]="0"
            enrich_metadata(tv,mapping_rows,ROOT,OUTPUT)
        finally:
            for k,v in old_env.items():
                if v is None: os.environ.pop(k,None)
                else: os.environ[k]=v
    else:
        print("[v15.1-selector] metadata enrichment skipped for fast recovery", flush=True)

'''
s=one(s,old,new,p); w(p,s)

# observer: Paddle fallback OFF by default
p='src/movie_gap_live_probe.py'; s=r(p)
if 'USE_PADDLE=' not in s: s=one(s,'MAX_WORKERS=max(1,min(10,int(os.environ.get("GAP_PROBE_WORKERS","8"))))\n','MAX_WORKERS=max(1,min(10,int(os.environ.get("GAP_PROBE_WORKERS","8"))))\nUSE_PADDLE=str(os.environ.get("GAP_PROBE_PADDLE","0")).strip().lower() in {"1","true","yes","on"}\n',p)
s=one(s,'''    for variant in plan:
        img=make(variant)
        if not img: continue
        add("paddleocr",variant,_paddle_ocr(img))
        chosen=_pick_title(candidates,channel_name,provider_name,profile)
        if chosen and chosen.get("confidence")=="high":
            break

''','''    if USE_PADDLE:
        for variant in plan:
            img=make(variant)
            if not img: continue
            add("paddleocr",variant,_paddle_ocr(img))
            chosen=_pick_title(candidates,channel_name,provider_name,profile)
            if chosen and chosen.get("confidence")=="high":
                break

''',p); w(p,s)

# candidate finder: parallel bounded source scan
p='src/movie_epg_recovery.py'; s=r(p)
if 'from concurrent.futures import ThreadPoolExecutor, as_completed' not in s: s=s.replace('import os\n','import os\nfrom concurrent.futures import ThreadPoolExecutor, as_completed\n',1)
start=s.find('    added, scanned, failed = [], [], []\n    if observations:\n'); end=s.find('\n    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)\n',start)
if start<0 or end<0: raise SystemExit('cannot patch candidate discovery')
block='''    added, scanned, failed = [], [], []
    if observations:
        timeout_cap=max(8,int(os.environ.get("EPG_DISCOVERY_TIMEOUT_CAP","25") or 25))
        workers=max(1,min(6,int(os.environ.get("EPG_DISCOVERY_WORKERS","4") or 4)))
        configs=[]
        for i,cfg in enumerate(load_sources()):
            if cfg.get("enabled",True) is False: continue
            groups=set(cfg.get("groups") or [])
            if groups and not (groups & TARGET_GROUPS): continue
            source_name=cfg.get("name") or cfg.get("id") or f"source-{i}"
            url=cfg.get("url") or cfg.get("xmltv") or cfg.get("epg_url") or ""
            if url: configs.append((i,source_name,url,cfg))

        def scan_source(spec):
            i,source_name,url,cfg=spec; src=None; matches=[]
            try:
                data=fetch_bytes(url,timeout=min(int(cfg.get("timeout",180) or 180),timeout_cap),retries=1,cache_bust_on_retry=False,cache_path=None,stale_if_error_seconds=0)
                src=XMLTVSource(source_name,data).index(); wanted=set(src.channels)
                for programme in src.fresh_programmes(wanted,past_days=1,future_days=1):
                    start_dt,stop_dt=_programme_window(programme)
                    if start_dt is None: continue
                    ptitle=programme_title(programme); sid=(programme.get("channel") or "").strip()
                    if not ptitle or not sid: continue
                    for obs in observations:
                        when=obs["when"]
                        if not (start_dt <= when and (stop_dt is None or when < stop_dt)): continue
                        score=evidence_similarity(ptitle,obs["title"])
                        if score < 0.82: continue
                        matches.append({"enabled":"1","playlist_name":obs["playlist_name"],"source":source_name,"source_id":sid,"notes":f"auto-discovered from live title; similarity={score:.3f}; observed={obs['title']}; candidate={ptitle}; requires two positive observations before selection"})
                return i,source_name,matches,None
            except Exception as exc:
                return i,source_name,[],type(exc).__name__
            finally:
                if src is not None:
                    try: src.release()
                    except Exception: pass

        results=[]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(scan_source,x) for x in configs]
            for future in as_completed(futures): results.append(future.result())
        for _,source_name,matches,error in sorted(results,key=lambda x:x[0]):
            if error:
                failed.append({"source":source_name,"error":error}); continue
            scanned.append(source_name)
            for item in matches:
                key=(item["playlist_name"],item["source"],item["source_id"])
                if key in keys: continue
                keys.add(key); existing.append(item); added.append(item)
'''
s=s[:start]+block+s[end:]; w(p,s)

# clean accidental/unsafe files
for rel in ['apply_adaptive_fast_movie_probe.py','apply_auto_epg_candidate_discovery.py','apply_fast_hourly_movie_recovery.py','apply_movie_zone_learning_fix.py','apply_role_based_movie_recovery.py','fix_movie_observer_runtime.py','src/live_verified_source_pins_patch.py','output/live-ocr-epg-state.json']:
    q=ROOT/rel
    if q.exists(): q.unlink()

# audit assertions
wf=[r(x) for x in ['.github/workflows/update.yml','.github/workflows/backfill-metadata.yml','.github/workflows/verify-movie-gaps.yml','.github/workflows/verify-existing-movie-epg.yml','.github/workflows/deploy-worker.yml']]
errors=[]
if any('epg-cache-${{ runner.os }}-${{ github.run_id }}' in x for x in wf): errors.append('run-id cache remains')
if 'apply_live_ocr_epg_overlay' in r('run.py'): errors.append('normal build still overlays OCR')
if 'live_ocr_epg_overlay' in r('.github/workflows/verify-existing-movie-epg.yml'): errors.append('verifier still overlays OCR')
if 'output/epg.xml.gz' in r('.github/workflows/verify-existing-movie-epg.yml'): errors.append('verifier still publishes EPG')
if 'if USE_PADDLE:' not in r('src/movie_gap_live_probe.py'): errors.append('Paddle gate missing')
if 'ThreadPoolExecutor' not in r('src/movie_epg_recovery.py'): errors.append('parallel discovery missing')
if 'RESELECT_SKIP_METADATA_ENRICH: "1"' not in r('.github/workflows/verify-movie-gaps.yml'): errors.append('metadata skip missing')
for bad in ['apply_adaptive_fast_movie_probe.py','apply_auto_epg_candidate_discovery.py','apply_fast_hourly_movie_recovery.py','apply_movie_zone_learning_fix.py','apply_role_based_movie_recovery.py','fix_movie_observer_runtime.py','src/live_verified_source_pins_patch.py']:
    if (ROOT/bad).exists(): errors.append('still present: '+bad)
if errors:
    print('AUDIT FAILED'); [print(' -',x) for x in errors]; sys.exit(1)
print('AUDIT OK')
print('Fixed workflow/cache/concurrency/OCR mutation/runtime/discovery/metadata-scan issues.')
