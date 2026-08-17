from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from .playlist import parse_m3u
from .state import save_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
PROTECTED_GROUPS = {"Кино", "Кинозалы", "Кино 4K", "Кинозалы UA"}
DEFAULT_WORKER_URL = "https://iptv-epg.peter96son.workers.dev/tv"


def _fresh_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != "fresh"]
    query.append(("fresh", "1"))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))


def _fetch_worker(url: str, timeout: int = 60) -> tuple[str, dict[str, str]]:
    request = urllib.request.Request(
        _fresh_url(url),
        headers={"User-Agent": "iptv-epg-builder-worker-audit/2.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
        headers = {k.lower(): v for k, v in response.headers.items()}
    return text, headers


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _validated_ids(postbuild: dict) -> set[str]:
    result = set()
    for row in postbuild.get("channels", []):
        if row.get("validated") and row.get("output_tvg_id"):
            result.add(str(row["output_tvg_id"]))
    return result


def audit_playlist(worker_text: str, mapping: dict[str, str], validated_ids: set[str]) -> tuple[list[dict], dict]:
    channels = parse_m3u(worker_text)
    rows: list[dict] = []
    seen_names = Counter(ch.name for ch in channels)

    # Audit every actual channel delivered by the Worker.
    for ch in channels:
        expected_id = str(mapping.get(ch.name, "") or "")
        actual_id = ch.tvg_id or ""
        issues: list[str] = []

        if expected_id:
            if actual_id != expected_id:
                issues.append("wrong_tvg_id")
            if expected_id not in validated_ids:
                issues.append("no_validated_programme")
        else:
            if ch.group in PROTECTED_GROUPS and (actual_id or ch.tvg_name):
                issues.append("protected_unmatched_has_epg_hint")
            if actual_id.lower().startswith("no_epg"):
                issues.append("placeholder_tvg_id_left")

        rows.append({
            "playlist_name": ch.name,
            "group": ch.group,
            "expected_tvg_id": expected_id,
            "actual_tvg_id": actual_id,
            "actual_tvg_name": ch.tvg_name,
            "epg_validated": bool(expected_id and expected_id in validated_ids),
            "duplicate_name_count": seen_names[ch.name],
            "status": "ok" if not issues else ";".join(issues),
        })

    delivered_names = set(seen_names)
    for name, expected_id in mapping.items():
        if name in delivered_names:
            continue
        rows.append({
            "playlist_name": name,
            "group": "",
            "expected_tvg_id": expected_id,
            "actual_tvg_id": "",
            "actual_tvg_name": "",
            "epg_validated": expected_id in validated_ids,
            "duplicate_name_count": 0,
            "status": "mapped_channel_missing_from_worker",
        })

    issue_counts = Counter()
    gap_rows = []
    for row in rows:
        if row["status"] == "ok":
            continue
        gap_rows.append(row)
        for issue in str(row["status"]).split(";"):
            issue_counts[issue] += 1

    summary = {
        "worker_channels": len(channels),
        "mapping_channels": len(mapping),
        "validated_epg_ids": len(validated_ids),
        "audited_rows": len(rows),
        "ok_rows": len(rows) - len(gap_rows),
        "gap_rows": len(gap_rows),
        "issue_counts": dict(issue_counts),
    }
    return rows, summary


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "playlist_name", "group", "expected_tvg_id", "actual_tvg_id",
        "actual_tvg_name", "epg_validated", "duplicate_name_count", "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def run() -> dict:
    OUTPUT.mkdir(exist_ok=True)
    worker_url = os.environ.get("WORKER_PLAYLIST_URL", DEFAULT_WORKER_URL).strip() or DEFAULT_WORKER_URL
    mapping_payload = _load_json(OUTPUT / "uhf-mapping.json", {})
    mapping = mapping_payload.get("channels", {}) if isinstance(mapping_payload, dict) else {}
    postbuild = _load_json(OUTPUT / "postbuild-validation.json", {})
    validated_ids = _validated_ids(postbuild)

    if not mapping:
        raise SystemExit("Worker audit: output/uhf-mapping.json has no channels")

    attempts = int(os.environ.get("WORKER_AUDIT_ATTEMPTS", "6"))
    delay = float(os.environ.get("WORKER_AUDIT_DELAY", "8"))
    last_error = ""
    best = None

    for attempt in range(1, attempts + 1):
        try:
            worker_text, headers = _fetch_worker(worker_url)
            rows, summary = audit_playlist(worker_text, mapping, validated_ids)
            summary.update({
                "worker_url": worker_url,
                "worker_version": headers.get("x-epg-worker-version", ""),
                "worker_cache": headers.get("x-epg-cache", ""),
                "worker_mapping_loaded": headers.get("x-epg-mapping-loaded", ""),
                "attempt": attempt,
            })
            best = (rows, summary)
            # A clean audit is final. Otherwise retry briefly because raw GitHub
            # content can lag the just-pushed commit for a few seconds.
            if summary["gap_rows"] == 0:
                break
        except Exception as exc:  # network diagnostics must not destroy the EPG build
            last_error = str(exc)
        if attempt < attempts:
            time.sleep(delay)

    if best is None:
        summary = {
            "worker_url": worker_url,
            "status": "fetch_failed",
            "error": last_error,
            "gap_rows": -1,
            "attempt": attempts,
        }
        rows = []
    else:
        rows, summary = best
        summary["status"] = "ok" if summary["gap_rows"] == 0 else "gaps_found"

    gaps = [row for row in rows if row.get("status") != "ok"]
    payload = {"summary": summary, "channels": rows}
    save_json(OUTPUT / "worker-audit.json", payload)
    _write_csv(OUTPUT / "worker-audit.csv", rows)
    _write_csv(OUTPUT / "worker-audit-gaps.csv", gaps)

    status_path = OUTPUT / "status.json"
    status = _load_json(status_path, {})
    if isinstance(status, dict):
        status["worker_audit"] = summary
        save_json(status_path, status)

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    run()
