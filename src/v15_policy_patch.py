"""v15 cumulative source-policy loader and safe physical-source de-duplication.

Imported before src.builder. It extends existing aliases/source_pins rather than
replacing them. Equivalent physical XMLTV URLs are downloaded once, but the
first source keeps its name/priority and inherits the union of scopes/caching
capabilities from later duplicate definitions.
"""
from __future__ import annotations
from urllib.parse import urlsplit, urlunsplit
from . import config as _config

_POLICY_PATH = _config.DATA / "source_policy_v15.csv"
_ORIGINAL_LOAD_ALIASES = _config.load_aliases
_ORIGINAL_LOAD_SOURCES = _config.load_sources


def _canonical_source_url(url: str) -> str:
    raw=(url or "").strip()
    if not raw:
        return ""
    try:
        p=urlsplit(raw)
    except ValueError:
        return raw.lower()
    host=(p.hostname or "").lower()
    if host.startswith("www."):
        host=host[4:]
    path=(p.path or "/").rstrip("/") or "/"
    return urlunsplit(("",host,path,p.query or "",""))


def _merge_scope(first: dict, duplicate: dict) -> None:
    for key in ("groups","group_scope","regions","region_scope","single_channel_playlist_names"):
        values=[]
        for source in (first,duplicate):
            current=source.get(key) or []
            if isinstance(current,str):
                current=[current]
            for item in current:
                if item not in values:
                    values.append(item)
        if values:
            first[key]=values
    first["timeout"]=max(int(first.get("timeout",0) or 0),int(duplicate.get("timeout",0) or 0))
    first["retries"]=max(int(first.get("retries",0) or 0),int(duplicate.get("retries",0) or 0))
    first["stale_if_error_seconds"]=max(
        int(first.get("stale_if_error_seconds",0) or 0),
        int(duplicate.get("stale_if_error_seconds",0) or 0),
    )
    for key in ("cache_fallback","cache_bust_on_retry","rescue_source"):
        if duplicate.get(key):
            first[key]=True


def load_sources_v15():
    sources=_ORIGINAL_LOAD_SOURCES()
    out=[]
    by_url={}
    for source in sources:
        url=source.get("url") or source.get("xmltv") or source.get("epg_url") or ""
        key=_canonical_source_url(url)
        if key and key in by_url:
            winner=by_url[key]
            _merge_scope(winner,source)
            print(f"[v15] duplicate physical EPG merged: {source.get('name','')} -> {winner.get('name','')}",flush=True)
            continue
        out.append(source)
        if key:
            by_url[key]=source
    return out


def load_aliases_v15():
    rows=_ORIGINAL_LOAD_ALIASES()
    rows.extend(_config._read_alias_csv(_POLICY_PATH))
    return rows


_config.load_sources=load_sources_v15
_config.load_aliases=load_aliases_v15
