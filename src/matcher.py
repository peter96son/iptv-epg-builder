from __future__ import annotations
from .utils import normalize_name, is_real_tvg_id
from .region import region_for_group, is_regional_sensitive, regions_compatible
from .channel_family import family_candidates


CONFIDENCE = {
    "alias": 100,
    "id": 99,
    "name-region": 96,
    "family-region": 92,
    "name": 90,
}


class Matcher:
    def __init__(self, aliases: list[dict]):
        self.alias_by_name = {}
        for row in aliases:
            if str(row.get("enabled", "1")).strip().lower() in {"0", "false", "no", "off"}:
                continue
            name = (row.get("playlist_name") or row.get("channel_name") or row.get("name") or "").strip()
            sid = (row.get("source_id") or row.get("epg_id") or row.get("target_id") or row.get("tvg_id") or "").strip()
            source = (row.get("source") or "").strip()
            provider_group = (row.get("provider_group") or row.get("group") or "").strip()
            region = (row.get("region") or row.get("country") or "").strip().upper()
            if name and sid:
                self.alias_by_name.setdefault(name, []).append((source, sid, provider_group, region))

    def _result(self, sid: str, method: str):
        return sid, method, CONFIDENCE[method]

    def match(self, channel, source, source_cfg: dict | None = None):
        source_cfg = source_cfg or {}
        channel_region = region_for_group(channel.group)
        source_regions = source_cfg.get("regions") or source_cfg.get("region_scope") or []

        # 1) manually researched mapping.
        for source_name, sid, provider_group, alias_region in self.alias_by_name.get(channel.name, []):
            if source_name and source_name != source.name:
                continue
            if provider_group and provider_group != channel.group:
                continue
            if alias_region and alias_region != channel_region:
                continue
            if sid in source.channels:
                return self._result(sid, "alias")

        # 2) exact provider ID.
        if is_real_tvg_id(channel.tvg_id) and channel.tvg_id in source.channels:
            if source_cfg.get("require_region_for_id"):
                if not regions_compatible(channel_region, source_regions):
                    return None, None, 0
            return self._result(channel.tvg_id, "id")

        # 3) exact normalized display-name.
        for candidate in (channel.name, channel.tvg_name):
            ids = source.names.get(normalize_name(candidate), set())
            if len(ids) != 1:
                continue
            if is_regional_sensitive(candidate):
                if not regions_compatible(channel_region, source_regions):
                    continue
                return self._result(next(iter(ids)), "name-region")
            return self._result(next(iter(ids)), "name")

        # 4) v3.0 regional family matching. This is intentionally available
        # ONLY for brands known to have country-specific schedules and ONLY
        # inside a source whose declared region matches the provider group.
        # It handles names such as "Discovery Science HD RO" vs
        # "Discovery Science" without opening the door to global fuzzy matches.
        for candidate in (channel.name, channel.tvg_name):
            if not candidate or not is_regional_sensitive(candidate):
                continue
            if not regions_compatible(channel_region, source_regions):
                continue
            families = family_candidates(candidate, channel_region)
            for family in families[1:]:
                ids = source.names.get(family, set())
                if len(ids) == 1:
                    return self._result(next(iter(ids)), "family-region")

        return None, None, 0
