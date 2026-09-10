from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import movie_gap_live_probe
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

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
PROBE = OUTPUT / "movie-gap-live-probe.json"
OBSERVATIONS = DATA / "live_epg_observations_v1518.csv"
CANDIDATES = DATA / "live_source_candidates_v1518.csv"
RECOVERY_REPORT = OUTPUT / "movie-epg-recovery.json"
TARGET_GROUPS = {"Кино", "USSR", "Кинозалы", "Кино 4K"}
OBS_FIELDS = ["enabled","observed_at","playlist_name","observed_title","origin","notes"]


def _norm(value):
    return " ".join(str(value or "").casefold().replace("ё","е").split())


def _load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_report(stage, payload):
    report = _load_json(RECOVERY_REPORT, {})
    if not isinstance(report, dict):
        report = {}
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    report.setdefault("stages", {})[stage] = payload
    RECOVERY_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def observe():
    # ROLE 1: observe only. Never edits EPG/mapping.
    rc = movie_gap_live_probe.main()
    probe = _load_json(PROBE, {})
    channels = probe.get("channels", {}) if isinstance(probe, dict) else {}
    recognized = []
    for row in channels.values():
        if not isinstance(row, dict) or row.get("group") not in TARGET_GROUPS:
            continue
        chosen = row.get("recognized_title")
        if isinstance(chosen, dict) and chosen.get("confidence") == "high" and chosen.get("title"):
            recognized.append({
                "playlist_name": row.get("playlist_name",""),
                "provider_name": row.get("provider_name",""),
                "title": chosen.get("title",""),
                "score": chosen.get("score",0),
                "zone": chosen.get("zone",""),
                "engine": chosen.get("engine",""),
            })
    result = {
        "return_code": rc,
        "channels_considered": probe.get("channels_considered",0),
        "high_confidence_observations": len(recognized),
        "recognized": recognized,
    }
    _write_report("observer", result)
    print("[movie-recovery:observer] " + json.dumps(result, ensure_ascii=False), flush=True)
    return result


def record_evidence():
    # ROLE 2: turn only high-confidence current observations into evidence.
    probe = _load_json(PROBE, {})
    generated_at = str(probe.get("generated_at") or datetime.now(timezone.utc).isoformat())
    channels = probe.get("channels", {}) if isinstance(probe, dict) else {}

    existing = []
    if OBSERVATIONS.exists():
        with OBSERVATIONS.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))

    seen = {
        (_norm(r.get("playlist_name")), _norm(r.get("observed_title")), str(r.get("observed_at",""))[:13])
        for r in existing
    }

    added = []
    rejected = []
    for row in channels.values():
        if not isinstance(row, dict) or row.get("group") not in TARGET_GROUPS:
            continue
        name = (row.get("playlist_name") or row.get("provider_name") or "").strip()
        chosen = row.get("recognized_title")
        if not isinstance(chosen, dict) or not chosen.get("title"):
            rejected.append({"playlist_name":name,"reason":"NO_TITLE"})
            continue
        if chosen.get("confidence") != "high":
            rejected.append({"playlist_name":name,"reason":"NOT_HIGH_CONFIDENCE"})
            continue

        title = str(chosen.get("title")).strip()
        key = (_norm(name), _norm(title), generated_at[:13])
        if key in seen:
            continue
        seen.add(key)
        item = {
            "enabled":"1",
            "observed_at":generated_at,
            "playlist_name":name,
            "observed_title":title,
            "origin":"movie-live-observer",
            "notes":f"high-confidence OCR; zone={chosen.get('zone','')}; engine={chosen.get('engine','')}; score={chosen.get('score',0)}",
        }
        existing.append(item)
        added.append(item)

    OBSERVATIONS.parent.mkdir(parents=True, exist_ok=True)
    with OBSERVATIONS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OBS_FIELDS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(existing)

    result = {"added":len(added),"rejected":len(rejected),"observations":added}
    _write_report("evidence_recorder", result)
    print("[movie-recovery:evidence] " + json.dumps(result, ensure_ascii=False), flush=True)
    return result



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

def select_donors():
    # ROLE 3/4: matcher + judge. Evidence layer must approve the donor.
    install_source_evidence(source_reselector)
    result = source_reselector.reselect_policy_sources()
    report = _load_json(OUTPUT / "source-selection-v15.json", {})
    selected = report.get("selected", {}) if isinstance(report, dict) else {}
    quarantined = report.get("quarantined", {}) if isinstance(report, dict) else {}
    payload = {
        "selector":result,
        "selected_count":len(selected),
        "quarantined_count":len(quarantined),
        "selected":selected,
        "quarantined":quarantined,
    }
    _write_report("judge", payload)
    print("[movie-recovery:judge] " + json.dumps(payload, ensure_ascii=False), flush=True)
    return payload


def audit():
    # ROLE 5: independent result measurement.
    summary = run_movie_audit(strict=False)
    _write_report("auditor", summary)
    print("[movie-recovery:auditor] " + json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("observe","record","discover","select","audit"))
    args = parser.parse_args()
    {"observe":observe,"record":record_evidence,"discover":discover_candidates,"select":select_donors,"audit":audit}[args.role]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
