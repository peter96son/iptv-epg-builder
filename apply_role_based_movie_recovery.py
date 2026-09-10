from pathlib import Path

root = Path(".")
module = root / "src/movie_epg_recovery.py"
workflow = root / ".github/workflows/verify-movie-gaps.yml"

module.write_text(r"""from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import movie_gap_live_probe
from .movie_epg_audit import run as run_movie_audit
import src.source_reselector as source_reselector
from .source_evidence import install as install_source_evidence

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
PROBE = OUTPUT / "movie-gap-live-probe.json"
OBSERVATIONS = DATA / "live_epg_observations_v1518.csv"
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
    parser.add_argument("role", choices=("observe","record","select","audit"))
    args = parser.parse_args()
    {"observe":observe,"record":record_evidence,"select":select_donors,"audit":audit}[args.role]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""", encoding="utf-8")

workflow.write_text(r"""name: Verify Missing Movie EPG

on:
  workflow_dispatch:
  schedule:
    - cron: "55 * * * *"

permissions:
  contents: write

concurrency:
  group: epg-metadata
  cancel-in-progress: false

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 55
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements-ocr.txt

      - name: Install OCR tools
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg tesseract-ocr tesseract-ocr-rus
          python -m pip install --upgrade pip
          python -m pip install -r requirements-ocr.txt

      - name: Dispatcher — identify movie EPG gaps
        env:
          PLAYLIST_URL: ${{ secrets.PLAYLIST_URL }}
        run: python -m src.movie_epg_recovery audit

      - name: Observer — read current title from live stream
        env:
          PLAYLIST_URL: ${{ secrets.PLAYLIST_URL }}
          STREAM_OCR_LANG: rus+eng
          GAP_PROBE_WORKERS: "6"
        run: python -m src.movie_epg_recovery observe

      - name: Evidence recorder — persist proven live titles
        run: python -m src.movie_epg_recovery record

      - name: Judge — select only evidence-matching EPG donors
        env:
          PLAYLIST_URL: ${{ secrets.PLAYLIST_URL }}
        run: python -m src.movie_epg_recovery select

      - name: Auditor — measure movie EPG after donor selection
        env:
          PLAYLIST_URL: ${{ secrets.PLAYLIST_URL }}
        run: python -m src.movie_epg_recovery audit

      - name: Publish evidence and proven donor results
        shell: bash
        run: |
          bash .github/scripts/safe-publish.sh "Recover movie EPG from live evidence"             data/live_epg_observations_v1518.csv             output/movie-gap-live-probe.json             output/movie-gap-ocr-profiles.json             output/movie-epg-recovery.json             output/source-selection-v15.json             output/mapping.csv             output/epg.xml.gz             output/uhf-mapping.json             output/movie-epg-audit.csv             output/movie-epg-audit.json             output/movie-epg-gaps.csv
""", encoding="utf-8")

print("changed:", module)
print("changed:", workflow)
