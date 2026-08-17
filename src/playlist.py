from __future__ import annotations
import re
from dataclasses import dataclass

ATTR = re.compile(r'([\w-]+)="([^"]*)"')

@dataclass
class PlaylistChannel:
    name: str
    tvg_id: str
    tvg_name: str
    group: str
    extinf: str = ""
    stream_url: str = ""

def parse_m3u(text: str) -> list[PlaylistChannel]:
    result = []
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF"):
            attrs = dict(ATTR.findall(line))
            name = line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "")
            pending = PlaylistChannel(
                name=name,
                tvg_id=attrs.get("tvg-id", "").strip(),
                tvg_name=attrs.get("tvg-name", "").strip(),
                group=attrs.get("group-title", "").strip(),
                extinf=raw,
            )
        elif pending and line and not line.startswith("#"):
            pending.stream_url = raw
            result.append(pending)
            pending = None
    return result
