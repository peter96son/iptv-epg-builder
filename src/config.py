from __future__ import annotations
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))

def load_sources():
    raw = load_json("sources.json")
    if isinstance(raw, dict):
        for key in ("sources", "items"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return raw if isinstance(raw, list) else []

def _read_alias_csv(path: Path):
    aliases = []
    if not path.exists():
        return aliases
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            aliases.append({k: (v or "").strip() for k, v in row.items()})
    return aliases

def load_aliases():
    # Normal researched aliases + hard source pins.
    # source_pins.csv intentionally uses the same schema as aliases.csv.
    aliases = _read_alias_csv(DATA / "aliases.csv")
    aliases.extend(_read_alias_csv(DATA / "source_pins.csv"))
    return aliases

def load_id_fixes():
    path = DATA / "tvg_id_fixes.csv"
    fixes = {}
    if not path.exists():
        return fixes
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("enabled", "1")).strip().lower() in {"0", "false", "no", "off"}:
                continue
            # v13 fix: existing project CSV uses playlist_name.
            name = (
                row.get("playlist_name")
                or row.get("channel_name")
                or row.get("name")
                or ""
            ).strip()
            new_id = (row.get("new_tvg_id") or row.get("tvg_id") or "").strip()
            if name and new_id:
                fixes[name] = new_id
    return fixes
