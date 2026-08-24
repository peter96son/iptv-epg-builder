from __future__ import annotations

"""v13.24: reject cached knowledge when a known programme year conflicts.

The normalized DB already stores year in its primary/cache keys, but resolve_knowledge()
historically allowed a yearless alias as a fallback even when the programme supplied a
year. That can map different works with the same translated title (e.g. "Шерлок Холмс")
onto the wrong IMDb entity.

This guard preserves all existing resolution logic, but when the caller knows a year,
a returned knowledge entity must carry the exact same year. Otherwise it is treated as
unresolved and the normal resolver continues to a better candidate/network lookup.
"""

from .metadata_db import MetadataDB, normalize_year

_original_resolve_knowledge = MetadataDB.resolve_knowledge

def _year_safe_resolve_knowledge(self, title, year="", media_type="", language=""):
    result = _original_resolve_knowledge(
        self, title, year=year, media_type=media_type, language=language
    )
    wanted = normalize_year(year)
    if not result or not wanted:
        return result

    resolved = normalize_year(result.get("year"))
    if resolved != wanted:
        return None
    return result

if not getattr(MetadataDB.resolve_knowledge, "_v1324_year_safe", False):
    _year_safe_resolve_knowledge._v1324_year_safe = True
    MetadataDB.resolve_knowledge = _year_safe_resolve_knowledge
