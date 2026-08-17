from __future__ import annotations
import gzip, json, os, shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_sources, load_aliases, load_id_fixes, load_json
from .matcher import Matcher
from .playlist import parse_m3u
from .reports import write_csv, write_status
from .utils import fetch_bytes, convert_xmltv_timestamp, is_real_tvg_id
from .xmltv import XMLTVSource
from .state import load_json as load_state_json, save_json
from .playlist_diff import snapshot_channels, compare_snapshots
from .dashboard import build_markdown, build_html
from .research import build_unmatched_family_reports

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"

def _source_url(source: dict) -> str:
    return source.get("url") or source.get("xmltv") or source.get("epg_url") or ""

def _source_name(source: dict, index: int) -> str:
    return source.get("name") or source.get("id") or f"source-{index}"

def _group_allowed(channel_group: str, source: dict) -> bool:
    groups = source.get("groups") or source.get("group_scope") or []
    return not groups or channel_group in groups

def _clone_channel(source_elem, out_id: str, display_name: str):
    elem = deepcopy(source_elem)
    elem.set("id", out_id)
    dn = ET.Element("display-name")
    dn.text = display_name
    elem.insert(0, dn)
    return elem

def build():
    OUTPUT.mkdir(exist_ok=True)
    playlist_url = os.environ.get("PLAYLIST_URL", "").strip()
    if not playlist_url:
        raise SystemExit("PLAYLIST_URL GitHub secret is missing.")

    priorities = load_json("priorities.json")
    timezone_name = priorities.get("timezone", "America/Los_Angeles")
    timezone = ZoneInfo(timezone_name)
    sources = load_sources()
    matcher = Matcher(load_aliases())
    id_fixes = load_id_fixes()

    playlist_text = fetch_bytes(playlist_url, timeout=60).decode("utf-8", "replace")
    channels = parse_m3u(playlist_text)
    if not channels:
        raise SystemExit("Playlist is empty or could not be parsed.")

    previous_snapshot_path = OUTPUT / "playlist-snapshot.json"
    previous_snapshot = load_state_json(previous_snapshot_path, [])
    current_snapshot = snapshot_channels(channels)
    playlist_changes = compare_snapshots(previous_snapshot, current_snapshot) if previous_snapshot else {
        "added_count": len(channels),
        "removed_count": 0,
        "renamed_count": 0,
        "stream_url_changed_count": 0,
        "group_changed_count": 0,
        "added": current_snapshot,
        "removed": [],
        "renamed": [],
        "stream_url_changed": [],
        "group_changed": [],
    }

    # Playlist collapse protection.
    if previous_snapshot:
        previous_count = len(previous_snapshot)
        current_count = len(current_snapshot)
        collapse_threshold = 0.15
        if previous_count >= 100 and current_count < previous_count * (1 - collapse_threshold):
            raise SystemExit(
                f"SAFETY STOP: playlist collapsed from {previous_count} to {current_count} channels."
            )

    unresolved = set(range(len(channels)))
    tv = ET.Element("tv", {"generator-info-name": "iptv-epg-builder"})
    emitted_channel_ids = set()
    mappings = []
    source_stats = []
    baseline_matched = 0
    baseline_groups = defaultdict(int)
    final_groups = defaultdict(int)
    programme_count = 0

    for source_index, source_cfg in enumerate(sources):
        url = _source_url(source_cfg)
        if not url:
            continue
        name = _source_name(source_cfg, source_index)
        candidates = [i for i in unresolved if _group_allowed(channels[i].group, source_cfg)]
        if not candidates:
            continue

        print(f"[{name}] downloading; candidates={len(candidates)}", flush=True)
        try:
            data = fetch_bytes(url, timeout=int(source_cfg.get("timeout", 180)), retries=2)
            source = XMLTVSource(name, data).index()
        except Exception as exc:
            print(f"[{name}] FAILED: {exc}", flush=True)
            source_stats.append({"source": name, "status": "failed", "matched": 0, "error": str(exc)})
            continue

        matches = {}
        by_source_id = defaultdict(list)
        for i in candidates:
            sid, method = matcher.match(channels[i], source)
            if sid:
                matches[i] = (sid, method)
                by_source_id[sid].append(i)

        if not matches:
            source_stats.append({"source": name, "status": "ok", "matched": 0})
            continue

        output_ids_for_source_id = defaultdict(list)
        for sid, indices in by_source_id.items():
            for i in indices:
                ch = channels[i]
                out_id = id_fixes.get(ch.name) or (ch.tvg_id if is_real_tvg_id(ch.tvg_id) else sid)
                if out_id not in output_ids_for_source_id[sid]:
                    output_ids_for_source_id[sid].append(out_id)
                if out_id not in emitted_channel_ids:
                    tv.append(_clone_channel(source.channels[sid], out_id, ch.name))
                    emitted_channel_ids.add(out_id)

        wanted_source_ids = set(output_ids_for_source_id)
        for programme in source.fresh_programmes(wanted_source_ids):
            sid = programme.get("channel", "")
            for out_id in output_ids_for_source_id.get(sid, []):
                p = deepcopy(programme)
                p.set("channel", out_id)
                for attr in ("start", "stop"):
                    if p.get(attr):
                        p.set(attr, convert_xmltv_timestamp(p.get(attr), timezone_name))
                tv.append(p)
                programme_count += 1

        if source_index == 0:
            baseline_matched = len(matches)
            for i in matches:
                baseline_groups[channels[i].group] += 1

        for i, (sid, method) in matches.items():
            ch = channels[i]
            output_tvg_id = id_fixes.get(ch.name) or (ch.tvg_id if is_real_tvg_id(ch.tvg_id) else sid)
            final_groups[ch.group] += 1
            mappings.append({
                "playlist_name": ch.name,
                "playlist_tvg_id": ch.tvg_id,
                "output_tvg_id": output_tvg_id,
                "group": ch.group,
                "source": name,
                "source_id": sid,
                "method": method,
            })
            unresolved.discard(i)

        source_stats.append({"source": name, "status": "ok", "matched": len(matches)})
        print(f"[{name}] matched={len(matches)} remaining={len(unresolved)}", flush=True)

    matched_total = len(channels) - len(unresolved)
    if programme_count == 0:
        raise SystemExit("SAFETY STOP: generated zero fresh programmes.")

    status_path = OUTPUT / "status.json"
    if status_path.exists():
        try:
            previous = json.loads(status_path.read_text(encoding="utf-8"))
            previous_programmes = int(previous.get("programmes", 0))
            max_drop = float(priorities.get("safety", {}).get("max_programme_drop_fraction", 0.40))
            if previous_programmes >= 1000 and programme_count < previous_programmes * (1 - max_drop):
                raise SystemExit(
                    f"SAFETY STOP: programme count fell from {previous_programmes} to {programme_count}."
                )
        except json.JSONDecodeError:
            pass

    tmp = OUTPUT / "epg.xml"
    ET.ElementTree(tv).write(tmp, encoding="utf-8", xml_declaration=True)
    with tmp.open("rb") as src, (OUTPUT / "epg.xml.gz").open("wb") as raw:
        with gzip.GzipFile(filename="epg.xml", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
    tmp.unlink()

    unmatched = [{
        "playlist_name": channels[i].name,
        "playlist_tvg_id": channels[i].tvg_id,
        "group": channels[i].group,
    } for i in sorted(unresolved)]

    family_report = build_unmatched_family_reports(unmatched, OUTPUT)
    unmatched_family_count = len(family_report.get("families", []))
    top_unmatched_families = [
        {
            "family": row.get("family"),
            "channels": row.get("channels", 0),
            "dummy_no_epg_ids": row.get("dummy_no_epg_ids", 0),
        }
        for row in family_report.get("families", [])[:20]
    ]

    added_by_group = {
        group: final_groups[group] - baseline_groups[group]
        for group in set(final_groups) | set(baseline_groups)
    }
    movie_groups = ["Кино", "Кино 4K", "Кинозалы", "Кинозалы UA"]
    movie_baseline = sum(baseline_groups[g] for g in movie_groups)
    movie_final = sum(final_groups[g] for g in movie_groups)

    group_coverage = {}
    playlist_group_totals = defaultdict(int)
    for ch in channels:
        playlist_group_totals[ch.group or "(без категории)"] += 1
    for group, total in sorted(playlist_group_totals.items()):
        base_n = baseline_groups[group]
        final_n = final_groups[group]
        group_coverage[group] = {
            "total": total,
            "baseline": base_n,
            "final": final_n,
            "added": final_n - base_n,
            "final_pct": round((final_n / total * 100), 1) if total else 0.0,
        }

    status = {
        "builder_version": "1.5",
        "generated_at": datetime.now(timezone).isoformat(),
        "timezone": timezone_name,
        "playlist_channels": len(channels),
        "baseline_matched_channels": baseline_matched,
        "final_matched_channels": matched_total,
        "added_by_fallback_channels": matched_total - baseline_matched,
        "unmatched_channels": len(unresolved),
        "unmatched_family_count": unmatched_family_count,
        "top_unmatched_families": top_unmatched_families,
        "programmes": programme_count,
        "sources": source_stats,
        "baseline_by_group": dict(baseline_groups),
        "final_by_group": dict(final_groups),
        "added_by_group": added_by_group,
        "group_totals": dict(playlist_group_totals),
        "group_coverage": group_coverage,
        "movie_priority": {
            "groups": movie_groups,
            "baseline": movie_baseline,
            "final": movie_final,
            "added": movie_final - movie_baseline,
        },
    }

    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if repo:
        public_epg_url = f"https://raw.githubusercontent.com/{repo}/main/output/epg.xml.gz"
        public_mapping_url = f"https://raw.githubusercontent.com/{repo}/main/output/uhf-mapping.json"
    else:
        public_epg_url = os.environ.get(
            "PUBLIC_EPG_URL",
            "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/epg.xml.gz",
        ).strip()
        public_mapping_url = ""

    # Publish only safe metadata. Never publish the provider M3U or stream URLs.
    uhf_mapping = {
        "generated_at": status.get("generated_at"),
        "epg_url": public_epg_url,
        "channels": {
            row["playlist_name"]: row["output_tvg_id"]
            for row in mappings
            if row.get("playlist_name") and row.get("output_tvg_id")
        },
    }
    save_json(OUTPUT / "uhf-mapping.json", uhf_mapping)

    # Delete a legacy public playlist created by v1.2/v1.3.
    legacy_public_playlist = OUTPUT / "playlist-uhf.m3u"
    if legacy_public_playlist.exists():
        legacy_public_playlist.unlink()

    status["uhf_delivery"] = {
        "mode": "cloudflare-worker",
        "epg_url": public_epg_url,
        "mapping_url": public_mapping_url,
        "public_playlist_published": False,
    }

    status["playlist_changes"] = {
        k: v for k, v in playlist_changes.items()
        if k.endswith("_count")
    }

    # Historical run summary.
    history_path = OUTPUT / "history.json"
    history = load_state_json(history_path, [])
    history.append({
        "generated_at": status.get("generated_at"),
        "playlist_channels": status.get("playlist_channels"),
        "baseline_matched_channels": status.get("baseline_matched_channels"),
        "final_matched_channels": status.get("final_matched_channels"),
        "added_by_fallback_channels": status.get("added_by_fallback_channels"),
        "unmatched_channels": status.get("unmatched_channels"),
        "programmes": status.get("programmes"),
        "sources": [
            {"source": s.get("source"), "status": s.get("status"), "matched": s.get("matched", 0)}
            for s in status.get("sources", [])
        ],
    })
    history = history[-180:]

    # Source cumulative ranking.
    source_totals = {}
    for run in history:
        for s in run.get("sources", []):
            name = s.get("source", "")
            if not name:
                continue
            row = source_totals.setdefault(name, {"runs": 0, "total_added": 0, "successful_runs": 0})
            row["runs"] += 1
            row["total_added"] += int(s.get("matched", 0) or 0)
            if s.get("status") == "ok":
                row["successful_runs"] += 1
    status["source_history_ranking"] = [
        {"source": name, **vals}
        for name, vals in sorted(source_totals.items(), key=lambda kv: -kv[1]["total_added"])
    ]

    # Persist diagnostics and dashboards.
    save_json(OUTPUT / "playlist-changes.json", playlist_changes)
    save_json(previous_snapshot_path, current_snapshot)
    save_json(history_path, history)
    (OUTPUT / "dashboard.md").write_text(build_markdown(status, playlist_changes, history), encoding="utf-8")
    (OUTPUT / "dashboard.html").write_text(build_html(status, playlist_changes, history), encoding="utf-8")

    write_status(status_path, status)
    write_csv(OUTPUT / "mapping.csv", mappings,
              ["playlist_name", "playlist_tvg_id", "output_tvg_id", "group", "source", "source_id", "method"])
    write_csv(OUTPUT / "unmatched.csv", unmatched,
              ["playlist_name", "playlist_tvg_id", "group"])


    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)
    return status
