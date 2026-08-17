from __future__ import annotations
import re
from dataclasses import dataclass

TVG_ID_RE = re.compile(r'(\btvg-id\s*=\s*)"[^"]*"')
URL_TVG_RE = re.compile(r'(\burl-tvg\s*=\s*)"[^"]*"')
X_TVG_URL_RE = re.compile(r'(\bx-tvg-url\s*=\s*)"[^"]*"')

@dataclass
class RewriteStats:
    channels_seen: int = 0
    ids_changed: int = 0
    ids_added: int = 0

def _replace_or_add_tvg_id(extinf_line: str, new_id: str) -> tuple[str, bool, bool]:
    if not new_id:
        return extinf_line, False, False

    old_value_match = re.search(r'\btvg-id\s*=\s*"([^"]*)"', extinf_line)
    if old_value_match:
        old_value = old_value_match.group(1)
        if old_value == new_id:
            return extinf_line, False, False
        new_line = TVG_ID_RE.sub(lambda m: f'{m.group(1)}"{new_id}"', extinf_line, count=1)
        return new_line, True, False

    if extinf_line.startswith("#EXTINF:"):
        parts = extinf_line.split(" ", 1)
        if len(parts) == 2:
            return f'{parts[0]} tvg-id="{new_id}" {parts[1]}', False, True
        if "," in extinf_line:
            head, tail = extinf_line.split(",", 1)
            return f'{head} tvg-id="{new_id}",{tail}', False, True

    return extinf_line, False, False

def _rewrite_header(line: str, epg_url: str) -> str:
    if not line.startswith("#EXTM3U"):
        return line

    if URL_TVG_RE.search(line):
        return URL_TVG_RE.sub(lambda m: f'{m.group(1)}"{epg_url}"', line, count=1)
    if X_TVG_URL_RE.search(line):
        return X_TVG_URL_RE.sub(lambda m: f'{m.group(1)}"{epg_url}"', line, count=1)
    return line.rstrip() + f' url-tvg="{epg_url}"'

def build_uhf_playlist(
    original_m3u: str,
    output_id_by_name: dict[str, str],
    epg_url: str,
) -> tuple[str, RewriteStats]:
    """
    Preserve provider M3U structure except for:
    - the EPG URL in #EXTM3U
    - verified tvg-id values aligned with generated XMLTV

    Stream URLs, logos, tvg-name, display names, #EXTGRP and ordering are preserved.
    """
    stats = RewriteStats()
    output = []

    for raw in original_m3u.splitlines():
        line = raw

        if line.startswith("#EXTM3U"):
            output.append(_rewrite_header(line, epg_url))
            continue

        if line.startswith("#EXTINF"):
            stats.channels_seen += 1
            name = line.split(",", 1)[1].strip() if "," in line else ""
            new_id = output_id_by_name.get(name, "")
            if new_id:
                line, changed, added = _replace_or_add_tvg_id(line, new_id)
                stats.ids_changed += int(changed)
                stats.ids_added += int(added)

        output.append(line)

    return "\n".join(output) + "\n", stats
