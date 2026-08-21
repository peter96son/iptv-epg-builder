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
        reader = csv.DictReader(f)
        expected = set(reader.fieldnames or [])
        for line_no, row in enumerate(reader, start=2):
            # DictReader stores surplus CSV columns under the None key.  A malformed
            # pin file must never crash the whole EPG build.
            extras = row.pop(None, None)
            if extras and any(str(v).strip() for v in extras):
                print(f"[config] WARNING: {path.name}:{line_no} has extra columns; row skipped", flush=True)
                continue
            clean = {str(k): str(v or "").strip() for k, v in row.items() if k is not None}
            if expected and set(clean) != expected:
                print(f"[config] WARNING: {path.name}:{line_no} has invalid schema; row skipped", flush=True)
                continue
            aliases.append(clean)
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
