from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _enabled(value: str) -> bool:
    return str(value or "1").strip().lower() not in {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def load_channel_time_offsets(path: str | Path | None = None) -> dict[tuple[str, str], int]:
    csv_path = Path(path) if path is not None else DATA / "channel_time_offsets.csv"
    offsets: dict[tuple[str, str], int] = {}
    if not csv_path.exists():
        return offsets

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):
            extras = row.pop(None, None)
            if extras and any(str(v).strip() for v in extras):
                print(f"[time-offsets] WARNING: {csv_path.name}:{line_no} has extra columns; row skipped", flush=True)
                continue
            if not _enabled(row.get("enabled", "1")):
                continue

            source = str(row.get("source", "") or "").strip()
            source_id = str(row.get("source_id", "") or "").strip()
            raw_minutes = str(row.get("offset_minutes", "") or "").strip()
            if not source or not source_id or not raw_minutes:
                continue
            if "*" in source_id[:-1] or source_id.count("*") > 1:
                continue
            try:
                minutes = int(raw_minutes)
            except ValueError:
                continue
            if abs(minutes) > 7 * 24 * 60:
                continue
            offsets[(source, source_id)] = minutes
    return offsets


def channel_time_offset_minutes(source: str, source_id: str) -> int:
    source = (source or "").strip()
    source_id = (source_id or "").strip()
    rules = load_channel_time_offsets()

    exact = rules.get((source, source_id))
    if exact is not None:
        return int(exact)

    best_prefix_len = -1
    best_minutes = 0
    for (rule_source, rule_source_id), minutes in rules.items():
        if rule_source != source or not rule_source_id.endswith("*"):
            continue
        prefix = rule_source_id[:-1]
        if source_id.startswith(prefix) and len(prefix) > best_prefix_len:
            best_prefix_len = len(prefix)
            best_minutes = int(minutes)
    return best_minutes
