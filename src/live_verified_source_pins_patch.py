"""v15.17 live-verified EPG source pins.

Installs before src.builder is imported.  It augments src.config in memory, so
the user's existing sources.json/source_pins.csv remain untouched.
"""
from __future__ import annotations
import src.config as _config

_ORIG_SOURCES = _config.load_sources
_ORIG_ALIASES = _config.load_aliases

TORRENT_TV = {
    "name": "torrent-tv",
    "url": "http://api.ttvrun.one/ttv.xmltv.xml.gz",
    "enabled": True,
    "timeout": 240,
    "retries": 2,
    "groups": ["Кино", "USSR", "Кинозалы", "Кино 4K"],
    "cache_fallback": True,
    "stale_if_error_seconds": 172800,
    "note": "v15.17 Torrent-TV XMLTV; use only for explicitly live-verified hard pins.",
}

LIVE_PINS = (
    {
        "enabled": "1",
        "playlist_name": "BCU VHS HD",
        "playlist_tvg_id": "Xbcu-vhs",
        "provider_group": "",
        "region": "",
        "source": "torrent-tv",
        "source_id": "ttv28064",
        "hard_pin": "1",
        "notes": "user live 2026-09-04: Адвокат дьявола; Torrent-TV BCU VHS broadcast_id 28064",
    },
    {
        "enabled": "1",
        "playlist_name": "BOX Oscar HD",
        "playlist_tvg_id": "Xbox-oscar",
        "provider_group": "",
        "region": "",
        "source": "torrent-tv",
        "source_id": "ttv29547",
        "hard_pin": "1",
        "notes": "user live 2026-09-04: Аватар; Torrent-TV BOX Oscar broadcast_id 29547",
    },
)

def _load_sources():
    sources = list(_ORIG_SOURCES())
    if not any(str(s.get("name","")) == "torrent-tv" for s in sources):
        # Put the live-verified source before generic rescue aggregators.
        insert_at = len(sources)
        for i, s in enumerate(sources):
            if s.get("rescue_source"):
                insert_at = i
                break
        sources.insert(insert_at, dict(TORRENT_TV))
    return sources

def _load_aliases():
    aliases = list(_ORIG_ALIASES())
    # Remove only competing rules for these two exact channels.  This makes
    # the live-verified mapping truly hard rather than another candidate.
    targets = {p["playlist_name"] for p in LIVE_PINS}
    aliases = [a for a in aliases if str(a.get("playlist_name","")).strip() not in targets]
    aliases.extend(dict(p) for p in LIVE_PINS)
    return aliases

_config.load_sources = _load_sources
_config.load_aliases = _load_aliases
