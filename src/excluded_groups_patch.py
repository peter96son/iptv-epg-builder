"""Apply playlist_rules exclude_groups before EPG matching.

Imported by run.py before src.builder. This keeps excluded country categories
out of the EPG/source-selection pipeline while preserving collapse protection:
the previous playlist snapshot is filtered by the same rule set before the
builder compares it with the new filtered snapshot.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import playlist as _playlist
from . import state as _state

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/"data"/"playlist_rules.json"

_ORIGINAL_PARSE_M3U=_playlist.parse_m3u
_ORIGINAL_STATE_LOAD_JSON=_state.load_json


def _excluded_groups()->set[str]:
    try:
        payload=json.loads(RULES.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {
        str(x).strip()
        for x in (payload.get("exclude_groups") or [])
        if str(x).strip()
    }


def _filter_channels(channels):
    excluded=_excluded_groups()
    if not excluded:
        return channels
    return [ch for ch in channels if getattr(ch,"group","") not in excluded]


def parse_m3u_filtered(text):
    return _filter_channels(_ORIGINAL_PARSE_M3U(text))


def load_state_json_filtered(path, default):
    value=_ORIGINAL_STATE_LOAD_JSON(path,default)
    try:
        name=Path(path).name
    except Exception:
        name=""
    if name!="playlist-snapshot.json" or not isinstance(value,list):
        return value
    excluded=_excluded_groups()
    if not excluded:
        return value
    return [
        row for row in value
        if not isinstance(row,dict) or row.get("group","") not in excluded
    ]


_playlist.parse_m3u=parse_m3u_filtered
_state.load_json=load_state_json_filtered
