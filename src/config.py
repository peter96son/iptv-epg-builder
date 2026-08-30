from __future__ import annotations
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

MOVIE_GROUPS = ["Кино", "USSR", "Кинозалы", "Кино 4K"]

def load_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))

def _ensure_group(source: dict, group: str) -> None:
    groups = list(source.get("groups") or [])
    if group not in groups:
        groups.append(group)
    source["groups"] = groups

def load_sources():
    raw = load_json("sources.json")
    if isinstance(raw, dict):
        for key in ("sources", "items"):
            if key in raw and isinstance(raw[key], list):
                sources = raw[key]
                break
        else:
            sources = []
    else:
        sources = raw if isinstance(raw, list) else []

    for source in sources:
        if source.get("name") == "iptv-online-primary":
            source["url"] = "https://iptv.online/epg/epg.xml.gz"
            source["enabled"] = True
            source["timeout"] = max(180, int(source.get("timeout", 0) or 0))
            source["note"] = (
                "REAL iptv.online provider EPG; first authority for provider tvg-id. "
                "Incomplete coverage is supplemented by rescue sources."
            )

    for source in sources:
        if source.get("name") in {"klimedia-dedicated", "bcumedia-dedicated"}:
            _ensure_group(source, "USSR")

    names = {str(s.get("name","")) for s in sources}

    if "premiere-group-dedicated" not in names:
        pg = {
            "name": "premiere-group-dedicated",
            "url": "http://epg-iptv.ru/premiere-group.xml",
            "enabled": True,
            "timeout": 120,
            "retries": 2,
            "groups": MOVIE_GROUPS,
            "cache_fallback": True,
            "stale_if_error_seconds": 172800,
            "note": "v14.14 Premiere Group dedicated EPG; live Premium HD mismatch proved generic Openbox mapping wrong."
        }
        insert_at = 0
        for i, source in enumerate(sources):
            if source.get("name") == "iptv-online-primary":
                insert_at = i + 1
                break
        sources.insert(insert_at, pg)
        names.add("premiere-group-dedicated")

    if "teleguide-rescue" not in names:
        sources.append({
            "name": "teleguide-rescue",
            "url": "https://teleguide.info/download/new3/xmltv.xml.gz",
            "enabled": True,
            "timeout": 240,
            "retries": 2,
            "groups": MOVIE_GROUPS,
            "rescue_source": True,
            "cache_fallback": True,
            "stale_if_error_seconds": 172800,
            "note": "Independent RU/CIS rescue; runtime freshness gate required."
        })
        names.add("teleguide-rescue")

    if "m3u-edit-all-rescue" not in names:
        sources.append({
            "name": "m3u-edit-all-rescue",
            "url": "https://m3u-edit.com/epg/ALL_SOURCES1.xml.gz",
            "enabled": True,
            "timeout": 600,
            "retries": 2,
            "groups": MOVIE_GROUPS,
            "rescue_source": True,
            "cache_fallback": True,
            "stale_if_error_seconds": 172800,
            "note": "v14.16 M3U-Edit ALL_SOURCES1 last-resort rescue for unresolved movie/USSR channels only."
        })
        names.add("m3u-edit-all-rescue")

    if "gabbarit-primary" not in names:
        sources.append({
            "name": "gabbarit-primary",
            "url": "http://gabbarit.drm-play.com/epg_1.xml.gz",
            "enabled": True,
            "timeout": 300,
            "retries": 2,
            "groups": MOVIE_GROUPS,
            "rescue_source": True,
            "cache_fallback": True,
            "stale_if_error_seconds": 172800,
            "note": "v13.23 movie rescue; current-week Gabbarit EPG."
        })
    if "gabbarit-mirror" not in names:
        sources.append({
            "name": "gabbarit-mirror",
            "url": "http://gabbarit.epg.one/epg_1.xml.gz",
            "enabled": True,
            "timeout": 300,
            "retries": 2,
            "groups": MOVIE_GROUPS,
            "rescue_source": True,
            "cache_fallback": True,
            "stale_if_error_seconds": 172800,
            "note": "v13.23 Gabbarit mirror; only used for still-unresolved movie channels."
        })

    if "epgone-full-movie-rescue" not in names:
        sources.append({
            "name": "epgone-full-movie-rescue",
            "url": "https://epg.one/epg.xml.gz",
            "enabled": True,
            "timeout": 300,
            "retries": 2,
            "groups": MOVIE_GROUPS,
            "rescue_source": True,
            "cache_fallback": True,
            "stale_if_error_seconds": 172800,
            "note": "v13.23 full epg.one movie rescue; includes newly-added provider cinema families."
        })

    return sources

def _read_alias_csv(path: Path):
    aliases = []
    if not path.exists():
        return aliases
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        expected = set(reader.fieldnames or [])
        for line_no, row in enumerate(reader, start=2):
            extras = row.pop(None, None)
            if extras and any(str(v).strip() for v in extras):
                # Never let a comma inside free-form notes disable a verified pin.
                if "notes" in row:
                    parts = [str(row.get("notes") or "").strip()]
                    parts.extend(str(v or "").strip() for v in extras)
                    row["notes"] = ", ".join(p for p in parts if p)
                    print(
                        f"[config] WARNING: {path.name}:{line_no} had extra note columns; merged into notes",
                        flush=True,
                    )
                else:
                    print(
                        f"[config] WARNING: {path.name}:{line_no} has extra columns and no notes field; row skipped",
                        flush=True,
                    )
                    continue
            clean = {str(k): str(v or "").strip() for k, v in row.items() if k is not None}
            if expected and set(clean) != expected:
                print(f"[config] WARNING: {path.name}:{line_no} has invalid schema; row skipped", flush=True)
                continue
            aliases.append(clean)
    return aliases

def load_aliases():
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
