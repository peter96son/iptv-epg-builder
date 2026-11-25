from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import movie_gap_live_probe
from .config import load_sources
from .movie_epg_audit import run as run_movie_audit
import src.source_reselector as source_reselector
from .source_evidence import (
    install as install_source_evidence,
    _similar as evidence_similarity,
    _title as programme_title,
    _norm as evidence_normalize,
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
SOURCE_CACHE = ROOT / ".cache" / "movie-recovery-sources"
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


def _source_bindings_for_consensus(observations):
    """Read source IDs from active policy, pins, durable bindings, or output mapping.

    Discovery suggestions require repeat evidence and must never vote as if they
    were already bound to a target channel.
    """
    paths = (
        DATA / "source_policy_v15.csv",
        DATA / "source_pins.csv",
        DATA / "epg-bindings.csv",
        OUTPUT / "mapping.csv",
    )
    names = {obs["playlist_name"] for obs in observations}
    bindings = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows = csv.DictReader(f)
                for row in rows:
                    if str(row.get("enabled", "1")).strip().lower() in {"0", "false", "no", "off"}:
                        continue
                    channel = (row.get("playlist_name") or "").strip()
                    source = (row.get("source") or "").strip()
                    source_id = (row.get("source_id") or "").strip()
                    if channel not in names or not source or not source_id:
                        continue
                    key = (channel, source)
                    values = bindings.setdefault(key, [])
                    if source_id not in values:
                        values.append(source_id)
        except (OSError, csv.Error):
            continue
    return bindings


def _schedule_only_observations(observations, observed_dt):
    """Add source-only checks for movie channels with multiple explicit bindings.

    These rows can report feed agreement and outliers, but they cannot claim
    that the majority matches the live stream. Only OCR observations provide
    that independent reference.
    """
    live_names = {obs["playlist_name"] for obs in observations if obs.get("title")}
    audit_path = OUTPUT / "movie-epg-audit.csv"
    if not audit_path.exists():
        return []
    try:
        with audit_path.open(encoding="utf-8-sig", newline="") as f:
            names = {
                (row.get("playlist_name") or "").strip()
                for row in csv.DictReader(f)
                if row.get("group") in TARGET_GROUPS and row.get("playlist_name")
            }
    except (OSError, csv.Error):
        return []
    bindings = _source_bindings_for_consensus(
        [{"playlist_name": name} for name in names]
    )
    by_channel = {}
    for (name, source), source_ids in bindings.items():
        if source_ids:
            by_channel.setdefault(name, set()).add(source)
    return [
        {
            "playlist_name": name,
            "title": "",
            "when": observed_dt,
            "reference_type": "BOUND_SCHEDULES",
        }
        for name, sources in sorted(by_channel.items())
        if name not in live_names and len(sources) >= 2
    ]


def _consensus_family(source_name, source_url, config):
    explicit = str(config.get("consensus_family") or "").strip().casefold()
    if explicit:
        return explicit
    host = (urlparse(source_url).hostname or "").casefold()
    return host or source_name.casefold()


def _summarize_source_votes(observations, votes):
    """Create per-channel source votes without counting mirrors as extra votes."""
    by_channel = {}
    for obs in observations:
        channel = obs["playlist_name"]
        current = [v for v in votes if v["playlist_name"] == channel]
        # A feed can expose several aliases for one channel. Let its first
        # configured binding vote once, so one provider cannot outvote others.
        per_family = {}
        for vote in current:
            family = vote["family"]
            existing = per_family.get(family)
            if existing is None or vote["priority"] < existing["priority"]:
                per_family[family] = vote
        grouped = {}
        for vote in per_family.values():
            grouped.setdefault(vote["title_norm"], []).append(vote)
        ordered = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
        _, top_votes = ordered[0] if ordered else ("", [])
        has_majority = bool(top_votes) and len(top_votes) >= 2 and len(top_votes) * 2 > len(per_family)
        live_title = str(obs.get("title") or "").strip()
        live_match = (
            max(
                (evidence_similarity(live_title, vote["title"]) for vote in top_votes),
                default=0.0,
            )
            if live_title
            else None
        )
        if live_title:
            if has_majority and live_match >= 0.82:
                status = "CONSENSUS"
            elif has_majority:
                status = "LIVE_TITLE_CONFLICT"
            elif len(per_family) >= 2:
                status = "NO_SOURCE_CONSENSUS"
            elif per_family:
                status = "INSUFFICIENT_INDEPENDENT_SOURCES"
            else:
                status = "NO_SCHEDULE_DATA"
        elif has_majority:
            status = "SOURCE_CONSENSUS_UNVERIFIED"
        elif len(per_family) >= 2:
            status = "SOURCE_DISAGREEMENT_UNVERIFIED"
        elif per_family:
            status = "INSUFFICIENT_INDEPENDENT_SOURCES"
        else:
            status = "NO_SCHEDULE_DATA"
        by_channel[channel] = {
            "status": status,
            "observed_at": obs["when"].isoformat(),
            "live_title": live_title,
            "reference_type": obs.get("reference_type", "LIVE_OCR"),
            "title": top_votes[0]["title"] if top_votes else "",
            "independent_sources": len(per_family),
            "consensus_votes": len(top_votes),
            "live_similarity": round(live_match, 4) if live_match is not None else None,
            "sources": [
                {k: vote[k] for k in ("source", "source_id", "family", "title", "title_norm", "similarity")}
                for vote in sorted(top_votes, key=lambda v: v["source"])
            ],
            "outliers": [
                {k: vote[k] for k in ("source", "source_id", "family", "title", "title_norm", "similarity")}
                for vote in sorted(
                    (v for key, group in ordered[1:] for v in group),
                    key=lambda v: (v["source"], v["title_norm"]),
                )
            ],
        }
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "channels": by_channel}


def _write_consensus(payload):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "movie-source-consensus.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
            observations.append({
                "playlist_name": name,
                "title": title,
                "when": observed_dt,
                "reference_type": "LIVE_OCR",
            })
    live_observed_names = {obs["playlist_name"] for obs in observations}
    schedule_only = _schedule_only_observations(observations, observed_dt)
    observations.extend(schedule_only)

    existing = []
    if CANDIDATES.exists():
        with CANDIDATES.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    keys = {
        ((r.get("playlist_name") or "").strip(), (r.get("source") or "").strip(), (r.get("source_id") or "").strip())
        for r in existing
    }

    bindings = _source_bindings_for_consensus(observations)

    added, scanned, failed, votes = [], [], [], []
    if observations:
        timeout_cap=max(8,int(os.environ.get("EPG_DISCOVERY_TIMEOUT_CAP","15") or 25))
        workers=max(1,min(6,int(os.environ.get("EPG_DISCOVERY_WORKERS","6") or 4)))

        # Accumulative recovery: once candidate donors are known for every
        # currently observed channel, re-check those sources first instead of
        # rescanning the whole source universe.
        candidate_sources_by_channel={}
        for row in existing:
            name=(row.get("playlist_name") or "").strip()
            source=(row.get("source") or "").strip()
            if name and source:
                candidate_sources_by_channel.setdefault(name,set()).add(source)

        observed_names=live_observed_names
        agreement_names={obs["playlist_name"] for obs in observations}
        focused_sources=set()
        needs_discovery=False
        for name in observed_names:
            known=candidate_sources_by_channel.get(name,set())
            if known:
                focused_sources.update(known)
            else:
                needs_discovery=True

        # Consensus checks only use IDs explicitly mapped to this playlist
        # channel. Matching a film somewhere else in a large XMLTV feed is not
        # evidence that the feed belongs to this channel.
        for (channel_name, source_name), source_ids in bindings.items():
            if channel_name in agreement_names and source_ids:
                focused_sources.add(source_name)

        configs=[]
        for i,cfg in enumerate(load_sources()):
            if cfg.get("enabled",True) is False: continue
            groups=set(cfg.get("groups") or [])
            if groups and not (groups & TARGET_GROUPS): continue
            source_name=cfg.get("name") or cfg.get("id") or f"source-{i}"
            if not needs_discovery and focused_sources and source_name not in focused_sources:
                continue
            url=cfg.get("url") or cfg.get("xmltv") or cfg.get("epg_url") or ""
            if url: configs.append((i,source_name,url,cfg))

        def scan_source(spec):
            i,source_name,url,cfg=spec; src=None; matches=[]; source_votes=[]
            try:
                cache_dir=Path(os.environ.get("EPG_RECOVERY_SOURCE_CACHE","") or SOURCE_CACHE)
                cache_dir.mkdir(parents=True,exist_ok=True)
                cache_file=cache_dir/f"{source_name}.bin"
                data=fetch_bytes(url,timeout=min(int(cfg.get("timeout",180) or 180),timeout_cap),retries=1,cache_bust_on_retry=False,cache_path=None,stale_if_error_seconds=0)
                try: cache_file.write_bytes(data)
                except Exception: pass
                src=XMLTVSource(source_name,data).index(); wanted=set(src.channels)
                family = _consensus_family(source_name, url, cfg)
                policy_ids = {
                    channel: ids
                    for (channel, mapped_source), ids in bindings.items()
                    if mapped_source == source_name
                }
                for programme in src.fresh_programmes(wanted,past_days=1,future_days=1):
                    start_dt,stop_dt=_programme_window(programme)
                    if start_dt is None: continue
                    ptitle=programme_title(programme); sid=(programme.get("channel") or "").strip()
                    if not ptitle or not sid: continue
                    for obs in observations:
                        when=obs["when"]
                        if not (start_dt <= when and (stop_dt is None or when < stop_dt)): continue
                        score=(
                            evidence_similarity(ptitle, obs["title"])
                            if obs.get("title")
                            else None
                        )
                        configured_ids = policy_ids.get(obs["playlist_name"], [])
                        title_norm = evidence_normalize(ptitle)
                        if sid in configured_ids and title_norm:
                            source_votes.append({
                                "playlist_name": obs["playlist_name"],
                                "source": source_name,
                                "source_id": sid,
                                "family": family,
                                "priority": configured_ids.index(sid),
                                "title": ptitle,
                                "title_norm": title_norm,
                                "similarity": round(score, 4) if score is not None else None,
                            })
                        if not obs.get("title") or score < 0.82: continue
                        matches.append({"enabled":"1","playlist_name":obs["playlist_name"],"source":source_name,"source_id":sid,"notes":f"auto-discovered from live title; similarity={score:.3f}; observed={obs['title']}; candidate={ptitle}; requires two positive observations before selection"})
                return i,source_name,matches,source_votes,None
            except Exception as exc:
                return i,source_name,[],[],type(exc).__name__
            finally:
                if src is not None:
                    try: src.release()
                    except Exception: pass

        results=[]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(scan_source,x) for x in configs]
            for future in as_completed(futures): results.append(future.result())
        for _,source_name,matches,source_votes,error in sorted(results,key=lambda x:x[0]):
            if error:
                failed.append({"source":source_name,"error":error}); continue
            scanned.append(source_name)
            votes.extend(source_votes)
            for item in matches:
                key=(item["playlist_name"],item["source"],item["source_id"])
                if key in keys: continue
                keys.add(key); existing.append(item); added.append(item)

    consensus = _summarize_source_votes(observations, votes)
    _write_consensus(consensus)

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
        "live_observations": len(live_observed_names),
        "schedule_only_channels": len(schedule_only),
        "sources_scanned": len(scanned),
        "sources_failed": failed,
        "candidates_added": len(added),
        "added": added,
        "source_consensus": consensus,
    }
    _write_report("candidate_discovery", result)
    print("[movie-recovery:discovery] " + json.dumps(result, ensure_ascii=False), flush=True)
    return result

def select_donors():
    # ROLE 3/4: accumulate proof across runs.
    # Repeated sightings of the SAME film are useful history but are not
    # independent proof. Automatic donor replacement starts only after two
    # distinct observed titles for the channel.
    probe=_load_json(PROBE,{})
    observed_now=[]
    for row in (probe.get("channels",{}) or {}).values():
        if not isinstance(row,dict) or row.get("group") not in TARGET_GROUPS:
            continue
        chosen=row.get("recognized_title")
        name=(row.get("playlist_name") or row.get("provider_name") or "").strip()
        if name and isinstance(chosen,dict) and chosen.get("confidence")=="high" and chosen.get("title"):
            observed_now.append(name)
    observed_now=sorted(set(observed_now))

    evidence_times={}
    evidence_titles={}
    if OBSERVATIONS.exists():
        with OBSERVATIONS.open(encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                if str(row.get("enabled","1")).strip().lower() in {"0","false","no","off"}:
                    continue
                name=(row.get("playlist_name") or "").strip()
                when=(row.get("observed_at") or "").strip()
                title=(row.get("observed_title") or "").strip()
                if not name or not when or not title:
                    continue
                evidence_times.setdefault(name,set()).add(when)
                evidence_titles.setdefault(name,set()).add(_norm(title))

    affected=sorted(
        name for name in observed_now
        if len(evidence_titles.get(name,set())) >= 2
    )
    pending={
        name:{
            "observations":len(evidence_times.get(name,set())),
            "distinct_titles":len(evidence_titles.get(name,set())),
            "status":"PENDING_DISTINCT_SECOND_TITLE",
        }
        for name in observed_now
        if name not in affected
    }

    if not affected:
        payload={
            "selector":{"changed":0,"selected":0,"reason":"waiting-for-distinct-second-title"},
            "pending_count":len(pending),
            "pending":pending,
            "selected_count":0,
            "quarantined_count":0,
            "selected":{},
            "quarantined":{},
        }
        _write_report("judge",payload)
        print("[movie-recovery:judge] "+json.dumps(payload,ensure_ascii=False),flush=True)
        return payload
    os.environ["RESELECT_ONLY_CHANNELS_JSON"]=json.dumps(affected,ensure_ascii=False)
    install_source_evidence(source_reselector)
    result = source_reselector.reselect_policy_sources()
    report = _load_json(OUTPUT / "source-selection-v15.json", {})
    selected = report.get("selected", {}) if isinstance(report, dict) else {}
    quarantined = report.get("quarantined", {}) if isinstance(report, dict) else {}
    payload = {
        "selector":result,
        "pending_count":len(pending),
        "pending":pending,
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
