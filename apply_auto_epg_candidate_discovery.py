from pathlib import Path

root = Path('.')
recovery = root / 'src/movie_epg_recovery.py'
reselector = root / 'src/source_reselector.py'
evidence = root / 'src/source_evidence.py'
workflow = root / '.github/workflows/verify-movie-gaps.yml'

s = recovery.read_text(encoding='utf-8')
s = s.replace('import json\n', 'import json\nimport os\n', 1)
s = s.replace(
'''from . import movie_gap_live_probe
from .movie_epg_audit import run as run_movie_audit
import src.source_reselector as source_reselector
from .source_evidence import install as install_source_evidence
''',
'''from . import movie_gap_live_probe
from .config import load_sources
from .movie_epg_audit import run as run_movie_audit
import src.source_reselector as source_reselector
from .source_evidence import (
    install as install_source_evidence,
    _similar as evidence_similarity,
    _title as programme_title,
)
from .utils import fetch_bytes, parse_xmltv_datetime
from .xmltv import XMLTVSource
''', 1)
s = s.replace(
    'OBSERVATIONS = DATA / "live_epg_observations_v1518.csv"\n',
    'OBSERVATIONS = DATA / "live_epg_observations_v1518.csv"\nCANDIDATES = DATA / "live_source_candidates_v1518.csv"\n', 1)

marker = '\ndef select_donors():\n'
if marker not in s:
    raise SystemExit('select_donors marker not found')

discovery = r'''

def _programme_window(programme):
    start = parse_xmltv_datetime(programme.get("start", ""))
    stop = parse_xmltv_datetime(programme.get("stop", "")) or start
    if start is None:
        return None, None
    start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)
    if stop is not None:
        stop = stop.replace(tzinfo=timezone.utc) if stop.tzinfo is None else stop.astimezone(timezone.utc)
    return start, stop


def discover_candidates():
    # Search every enabled movie EPG source for the observed live title at the same time.
    probe = _load_json(PROBE, {})
    observed_at = str(probe.get("generated_at") or "")
    try:
        observed_dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed_dt.tzinfo is None:
            observed_dt = observed_dt.replace(tzinfo=timezone.utc)
        observed_dt = observed_dt.astimezone(timezone.utc)
    except Exception:
        observed_dt = datetime.now(timezone.utc)

    observations = []
    for row in (probe.get("channels", {}) or {}).values():
        if not isinstance(row, dict) or row.get("group") not in TARGET_GROUPS:
            continue
        chosen = row.get("recognized_title")
        if not isinstance(chosen, dict) or chosen.get("confidence") != "high":
            continue
        title = str(chosen.get("title") or "").strip()
        name = (row.get("playlist_name") or row.get("provider_name") or "").strip()
        if title and name:
            observations.append({"playlist_name": name, "title": title, "when": observed_dt})

    existing = []
    if CANDIDATES.exists():
        with CANDIDATES.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    keys = {
        ((r.get("playlist_name") or "").strip(), (r.get("source") or "").strip(), (r.get("source_id") or "").strip())
        for r in existing
    }

    added, scanned, failed = [], [], []
    if observations:
        timeout_cap = max(10, int(os.environ.get("EPG_DISCOVERY_TIMEOUT_CAP", "60") or 60))
        for i, cfg in enumerate(load_sources()):
            if cfg.get("enabled", True) is False:
                continue
            groups = set(cfg.get("groups") or [])
            if groups and not (groups & TARGET_GROUPS):
                continue
            source_name = cfg.get("name") or cfg.get("id") or f"source-{i}"
            url = cfg.get("url") or cfg.get("xmltv") or cfg.get("epg_url") or ""
            if not url:
                continue
            src = None
            try:
                data = fetch_bytes(
                    url,
                    timeout=min(int(cfg.get("timeout", 180) or 180), timeout_cap),
                    retries=1,
                    cache_bust_on_retry=False,
                    cache_path=None,
                    stale_if_error_seconds=0,
                )
                src = XMLTVSource(source_name, data).index()
                scanned.append(source_name)
                wanted = set(src.channels)
                for programme in src.fresh_programmes(wanted, past_days=1, future_days=1):
                    start, stop = _programme_window(programme)
                    if start is None:
                        continue
                    ptitle = programme_title(programme)
                    sid = (programme.get("channel") or "").strip()
                    if not ptitle or not sid:
                        continue
                    for obs in observations:
                        when = obs["when"]
                        if not (start <= when and (stop is None or when < stop)):
                            continue
                        score = evidence_similarity(ptitle, obs["title"])
                        if score < 0.82:
                            continue
                        key = (obs["playlist_name"], source_name, sid)
                        if key in keys:
                            continue
                        keys.add(key)
                        item = {
                            "enabled": "1",
                            "playlist_name": obs["playlist_name"],
                            "source": source_name,
                            "source_id": sid,
                            "notes": (
                                f"auto-discovered from live title; similarity={score:.3f}; "
                                f"observed={obs['title']}; candidate={ptitle}; "
                                "requires two positive observations before selection"
                            ),
                        }
                        existing.append(item)
                        added.append(item)
            except Exception as exc:
                failed.append({"source": source_name, "error": type(exc).__name__})
            finally:
                if src is not None:
                    try:
                        src.release()
                    except Exception:
                        pass

    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["enabled", "playlist_name", "source", "source_id", "notes"],
            extrasaction="ignore",
            lineterminator="\n",
        )
        w.writeheader()
        w.writerows(existing)

    result = {
        "live_observations": len(observations),
        "sources_scanned": len(scanned),
        "sources_failed": failed,
        "candidates_added": len(added),
        "added": added,
    }
    _write_report("candidate_discovery", result)
    print("[movie-recovery:discovery] " + json.dumps(result, ensure_ascii=False), flush=True)
    return result
'''

s = s.replace(marker, discovery + marker, 1)
s = s.replace('choices=("observe","record","select","audit")', 'choices=("observe","record","discover","select","audit")', 1)
s = s.replace(
    '{"observe":observe,"record":record_evidence,"select":select_donors,"audit":audit}[args.role]()',
    '{"observe":observe,"record":record_evidence,"discover":discover_candidates,"select":select_donors,"audit":audit}[args.role]()',
    1,
)
recovery.write_text(s, encoding='utf-8')

s = reselector.read_text(encoding='utf-8')
needle = '''                "evidence_required":_requires_evidence(rows),
            }'''
replacement = '''                "evidence_required":_requires_evidence(rows),
                "min_evidence":2 if "auto-discovered from live title" in (row.get("notes") or "") else 1,
            }'''
if needle not in s:
    raise SystemExit('reselector candidate block not found')
reselector.write_text(s.replace(needle, replacement, 1), encoding='utf-8')

s = evidence.read_text(encoding='utf-8')
needle = '''            best_positive = max(
                (c["_evidence_positive"] for c in clean),
                default=0,
            )
            if best_positive > 0:
                winners = [
                    c for c in clean
                    if c["_evidence_positive"] == best_positive
                ]'''
replacement = '''            eligible = [
                c for c in clean
                if c["_evidence_positive"] >= int(c.get("min_evidence", 1) or 1)
            ]
            best_positive = max(
                (c["_evidence_positive"] for c in eligible),
                default=0,
            )
            if best_positive > 0:
                winners = [
                    c for c in eligible
                    if c["_evidence_positive"] == best_positive
                ]'''
if needle not in s:
    raise SystemExit('evidence winner block not found')
evidence.write_text(s.replace(needle, replacement, 1), encoding='utf-8')

w = workflow.read_text(encoding='utf-8')
judge = '      - name: Judge — select only evidence-matching EPG donors\n'
step = '''      - name: Candidate finder — search all movie EPG sources
        env:
          EPG_DISCOVERY_TIMEOUT_CAP: "60"
        run: python -m src.movie_epg_recovery discover

'''
if step not in w:
    if judge not in w:
        raise SystemExit('workflow judge marker not found')
    w = w.replace(judge, step + judge, 1)
if 'data/live_source_candidates_v1518.csv' not in w:
    w = w.replace(
        'data/live_epg_observations_v1518.csv',
        'data/live_epg_observations_v1518.csv             data/live_source_candidates_v1518.csv             data/source_evidence_state.json',
        1,
    )
workflow.write_text(w, encoding='utf-8')

print('changed:', recovery)
print('changed:', reselector)
print('changed:', evidence)
print('changed:', workflow)
