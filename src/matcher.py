from __future__ import annotations
from collections import defaultdict
from .utils import normalize_name, is_real_tvg_id

class Matcher:
    def __init__(self, aliases: list[dict]):
        self.alias_by_name = {}
        for row in aliases:
            name = (row.get("playlist_name") or row.get("channel_name") or row.get("name") or "").strip()
            sid = (row.get("source_id") or row.get("epg_id") or row.get("target_id") or row.get("tvg_id") or "").strip()
            source = (row.get("source") or "").strip()
            if name and sid:
                self.alias_by_name.setdefault(name, []).append((source, sid))

    def match(self, channel, source):
        # 1) manually researched mapping
        for source_name, sid in self.alias_by_name.get(channel.name, []):
            if (not source_name or source_name == source.name) and sid in source.channels:
                return sid, "alias"

        # 2) provider tvg-id
        if is_real_tvg_id(channel.tvg_id) and channel.tvg_id in source.channels:
            return channel.tvg_id, "id"

        # 3) exact normalized display-name, only when unambiguous
        for candidate in (channel.name, channel.tvg_name):
            ids = source.names.get(normalize_name(candidate), set())
            if len(ids) == 1:
                return next(iter(ids)), "name"

        return None, None
