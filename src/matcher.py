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
        self.alias_by_normalized_name = {}
        self.pinned_sources_by_name = {}
        self.pinned_sources_by_normalized_name = {}
        for row in aliases:
            if str(row.get("enabled", "1")).strip().lower() in {"0", "false", "no", "off"}:
                continue
            name = (row.get("playlist_name") or row.get("channel_name") or row.get("name") or "").strip()
            sid = (row.get("source_id") or row.get("epg_id") or row.get("target_id") or row.get("tvg_id") or "").strip()
            source = (row.get("source") or "").strip()
            provider_group = (row.get("provider_group") or row.get("group") or "").strip()
            region = (row.get("region") or row.get("country") or "").strip().upper()
            hard_pin = str(row.get("hard_pin", "")).strip().lower() in {"1", "true", "yes", "on"}
            if name and sid:
                item=(source, sid, provider_group, region)
                self.alias_by_name.setdefault(name, []).append(item)
                norm=normalize_name(name)
                if norm:
                    self.alias_by_normalized_name.setdefault(norm, []).append(item)
                if hard_pin and source:
                    self.pinned_sources_by_name.setdefault(name, set()).add(source)
                    if norm:
                        self.pinned_sources_by_normalized_name.setdefault(norm, set()).add(source)

    def _result(self, sid: str, method: str):
        return sid, method, CONFIDENCE[method]

    def _aliases_for_channel(self, channel):
        exact=self.alias_by_name.get(channel.name)
        if exact:
            return exact
        return self.alias_by_normalized_name.get(normalize_name(channel.name), [])

    def _pins_for_channel(self, channel):
        exact=self.pinned_sources_by_name.get(channel.name)
        if exact:
            return exact
        return self.pinned_sources_by_normalized_name.get(normalize_name(channel.name))

    def _source_allowed(self, channel, source, source_cfg: dict | None = None) -> bool:
        source_cfg = source_cfg or {}
        pinned = self._pins_for_channel(channel)
        return (
            not pinned
            or source.name in pinned
            or bool(source_cfg.get("rescue_source"))
        )

    def match(self, channel, source, source_cfg: dict | None = None, *, allow_family: bool = True):
        source_cfg = source_cfg or {}
        if not self._source_allowed(channel, source, source_cfg):
            return None, None, 0
        channel_region = region_for_group(channel.group)
        source_regions = source_cfg.get("regions") or source_cfg.get("region_scope") or []
        for source_name, sid, provider_group, alias_region in self._aliases_for_channel(channel):
            if source_name and source_name != source.name:
                continue
            if provider_group and provider_group != channel.group:
                continue
            if alias_region and alias_region != channel_region:
                continue
            if sid in source.channels:
                return self._result(sid, "alias")
        if is_real_tvg_id(channel.tvg_id) and channel.tvg_id in source.channels:
            if source_cfg.get("require_region_for_id") and not regions_compatible(channel_region, source_regions):
                return None, None, 0
            return self._result(channel.tvg_id, "id")
        for candidate in (channel.name, channel.tvg_name):
            candidate_keys = [normalize_name(candidate)]
            # v14.14 Premiere Group EPG often labels channels with an SPG prefix
            # while provider playlists use names such as "Premium HD".
            if source.name == "premiere-group-dedicated" and candidate:
                candidate_keys.append(normalize_name(f"SPG {candidate}"))
            ids = set()
            for key in candidate_keys:
                ids.update(source.names.get(key, set()))
            if len(ids) != 1:
                continue
            if is_regional_sensitive(candidate):
                if not regions_compatible(channel_region, source_regions):
                    continue
                return self._result(next(iter(ids)), "name-region")
            return self._result(next(iter(ids)), "name")
        if not allow_family:
            return None, None, 0
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

    def match_family(self, channel, source, source_cfg: dict | None = None):
        source_cfg = source_cfg or {}
        if not self._source_allowed(channel, source, source_cfg):
            return None, None, 0
        channel_region = region_for_group(channel.group)
        source_regions = source_cfg.get("regions") or source_cfg.get("region_scope") or []
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
