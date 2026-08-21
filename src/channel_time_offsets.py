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
    """Load per-source/per-channel XMLTV offsets in minutes.

    Keys are (source_name, source_id). A rule therefore affects exactly one
    channel inside one upstream source and cannot shift sibling channels.
    Malformed rows fail closed: they are skipped with a warning.
    """
    csv_path = Path(path) if path is not None else DATA / "channel_time_offsets.csv"
    offsets: dict[tuple[str, str], int] = {}
    if not csv_path.exists():
        return offsets

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):
            extras = row.pop(None, None)
            if extras and any(str(v).strip() for v in extras):
                print(
                    f"[time-offsets] WARNING: {csv_path.name}:{line_no} has extra columns; row skipped",
                    flush=True,
                )
                continue
            if not _enabled(row.get("enabled", "1")):
                continue

            source = str(row.get("source", "") or "").strip()
            source_id = str(row.get("source_id", "") or "").strip()
            raw_minutes = str(row.get("offset_minutes", "") or "").strip()
            if not source or not source_id or not raw_minutes:
                print(
                    f"[time-offsets] WARNING: {csv_path.name}:{line_no} missing source/source_id/offset; row skipped",
                    flush=True,
                )
                continue
            try:
                minutes = int(raw_minutes)
            except ValueError:
                print(
                    f"[time-offsets] WARNING: {csv_path.name}:{line_no} invalid offset_minutes={raw_minutes!r}; row skipped",
                    flush=True,
                )
                continue
            if abs(minutes) > 7 * 24 * 60:
                print(
                    f"[time-offsets] WARNING: {csv_path.name}:{line_no} offset too large; row skipped",
                    flush=True,
                )
                continue
            offsets[(source, source_id)] = minutes
    return offsets


def channel_time_offset_minutes(source: str, source_id: str) -> int:
    return int(load_channel_time_offsets().get(((source or "").strip(), (source_id or "").strip()), 0))
