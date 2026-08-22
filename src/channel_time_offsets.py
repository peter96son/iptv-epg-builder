from __future__ import annotations
import csv
from functools import lru_cache
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
def _enabled(value: str) -> bool:
    return str(value or "1").strip().lower() not in {"0","false","no","off"}
@lru_cache(maxsize=1)
def load_channel_time_offsets(path: str | Path | None = None) -> dict[tuple[str,str],int]:
    csv_path = Path(path) if path is not None else DATA / "channel_time_offsets.csv"
    offsets = {}
    if not csv_path.exists(): return offsets
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            extras = row.pop(None, None)
            if extras and any(str(v).strip() for v in extras): continue
            if not _enabled(row.get("enabled","1")): continue
            source = str(row.get("source","") or "").strip()
            source_id = str(row.get("source_id","") or "").strip()
            raw = str(row.get("offset_minutes","") or "").strip()
            if not source or not source_id or not raw: continue
            if "*" in source_id[:-1] or source_id.count("*") > 1: continue
            try: minutes = int(raw)
            except ValueError: continue
            if abs(minutes) > 7*24*60: continue
            offsets[(source,source_id)] = minutes
    return offsets
def channel_time_offset_minutes(source: str, source_id: str) -> int:
    source=(source or "").strip(); source_id=(source_id or "").strip()
    rules=load_channel_time_offsets()
    exact=rules.get((source,source_id))
    if exact is not None: return int(exact)
    best_len=-1; best=0
    for (rs,rid),minutes in rules.items():
        if rs != source or not rid.endswith("*"): continue
        prefix=rid[:-1]
        if source_id.startswith(prefix) and len(prefix)>best_len:
            best_len=len(prefix); best=int(minutes)
    return best
