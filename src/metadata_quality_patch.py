"""Metadata quality guards for IPTV EPG Builder v11.0.

This module is intentionally small and loaded for its side effects before
``src.builder``.  It wraps the lookup/cache helpers in metadata_enrichment
without duplicating the enrichment engine.

Guards:
- reject unsafe transliteration matches;
- preserve significant sequel/part numbers;
- prevent dotted subtitles from collapsing to an unrelated series root;
- force legacy positive cache rows without confidence/overview/genres to refresh.

Precision first: a missed enrichment is preferable to a wrong IMDb identity.
"""
from __future__ import annotations

import re

from . import metadata_enrichment as me
from .utils import normalize_name

PATCH_VERSION = "11.2"

# Keep reporting/versioning aligned with the v11 engine.
me.METADATA_VERSION = PATCH_VERSION
me.CACHE_SCHEMA = max(int(getattr(me, "CACHE_SCHEMA", 0) or 0), 12)

_ORIG_LOOKUP = me._tmdb_lookup_imdb
_ORIG_SANITIZE = me._sanitize_cache_entry

_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")
_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:х/ф|м/ф|т/с|д/с|д/ф|сериал|фильм|кино)\s*[:.\-–—]?\s*"
)
_AGE_RE = re.compile(r"\s*[\[(]\s*\d{1,2}\+\s*[\])]\s*")


def _significant_numbers(text: str) -> tuple[str, ...]:
    """Return content-significant numbers, excluding likely calendar years."""
    out: list[str] = []
    for token in _NUMBER_RE.findall(text or ""):
        try:
            number = int(token)
        except ValueError:
            continue
        if 1900 <= number <= 2099:
            continue
        out.append(str(number))
    return tuple(out)


def _raw_title_for_number_guard(raw_title: str) -> str:
    value = _PREFIX_RE.sub("", raw_title or "")
    value = _AGE_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


def _meaningful_source_numbers(raw_title: str) -> tuple[str, ...]:
    """Keep sequel/part numbers while ignoring a trailing episode marker.

    Examples:
      ``Лютый 2. 1 с.`` -> ("2",)
      ``Динотопия, 2 с`` -> ()   # the 2 is an episode/part marker in provider EPG
      ``Люди в черном 3`` -> ("3",)
    """
    value = _raw_title_for_number_guard(raw_title)

    # Remove trailing EPG episode/range notation before examining identity numbers.
    value = re.sub(
        r"(?i)[,.;:]?\s*\d+\s*(?:и|і|&|and|-|–|—)\s*\d+\s*[сc]\.?\s*$",
        "",
        value,
    )
    value = re.sub(r"(?i)[,.;:]?\s*\d+\s*[сc]\.?\s*$", "", value)
    value = re.sub(r"(?i)\s+(?:серия|сер\.|эпизод|episode)\s*\d+\b.*$", "", value)

    return _significant_numbers(value)


def _translit_candidate_is_safe(
    raw_title: str,
    query_title: str,
    result: dict,
) -> tuple[bool, str]:
    """Apply stricter acceptance rules to transliteration-based matches."""
    original_clean = me._clean_search_title(raw_title or "")
    expected_translit = me._transliterate_ru(original_clean)

    source_numbers = _meaningful_source_numbers(raw_title)
    query_numbers = _significant_numbers(query_title)

    if source_numbers and not set(source_numbers).issubset(set(query_numbers)):
        return False, "translit_lost_significant_number"

    candidate_names = [
        str(result.get("title") or ""),
        str(result.get("original_title") or ""),
    ]
    candidate_names = [name for name in candidate_names if name]
    if not candidate_names:
        return False, "translit_missing_candidate_title"

    similarities = [
        me._title_similarity(expected_translit, candidate_name)
        for candidate_name in candidate_names
    ]
    best = max(similarities, default=0.0)
    if best < 0.93:
        return False, f"translit_candidate_diverged:{best:.3f}"

    confidence = int(result.get("confidence") or 0)
    if confidence < 96:
        return False, f"translit_low_confidence:{confidence}"

    return True, ""


def _series_root_is_safe(raw_title: str, query_title: str) -> tuple[bool, str]:
    """Allow root fallback only when the suffix is clearly non-identity metadata."""
    cleaned = me._clean_search_title(raw_title or "")
    if ". " not in cleaned:
        return True, ""

    root, suffix = cleaned.split(". ", 1)
    root = root.strip()
    suffix = suffix.strip()

    # Existing provider family: region follows the common franchise root.
    if normalize_name(root) == normalize_name("Наш спецназ") and suffix:
        return True, ""

    # Numeric season/episode fragment is safe to collapse.
    if re.fullmatch(r"(?i)(?:сезон\s*)?\d+(?:\s*[сc])?\.?", suffix):
        return True, ""

    # Anything lexical after the dot may be a real subtitle/sequel identity.
    return False, "series_root_preserved_subtitle"


def _sanitize_cache_entry_v11(value: dict) -> dict:
    """Normalize legacy entries without throwing away a trusted identity.

    v11.2 separates *identity trust* from *display completeness*:
    - missing confidence => identity is not trusted and must be re-resolved;
    - confidence + IMDb identity => keep it, even if genres/overview are absent;
      mark it for opportunistic display refresh instead of causing a cold lookup.
    """
    out = _ORIG_SANITIZE(value)

    if out.get("status") != "found":
        return out

    if not str(out.get("confidence") or "").strip():
        return {
            "status": "legacy_unscored",
            "resolver": "tmdb",
            "cached_at": "",
            "miss_count": 0,
            "legacy_imdb_id": str(out.get("imdb_id") or ""),
            "legacy_reason": "missing_confidence_revalidate_v11",
        }

    missing_genres = not bool(out.get("genre_ids"))
    missing_overview = not str(out.get("overview") or "").strip()
    if missing_genres or missing_overview:
        out["needs_display_refresh"] = True
        out.setdefault("legacy_reason", "missing_genre_overview_refresh_v11_2")
    else:
        out.pop("needs_display_refresh", None)

    return out


def _tmdb_lookup_imdb_v11(*args, **kwargs) -> dict:
    """Wrap the normal TMDb lookup with precision guards."""
    result = _ORIG_LOOKUP(*args, **kwargs)

    if result.get("status") != "found":
        return result

    attempt = str(result.get("attempt") or "")
    raw_title = str(
        kwargs.get("raw_title")
        or (args[6] if len(args) > 6 else "")
    )
    query_title = str(result.get("query_title") or "")

    if attempt.startswith("translit"):
        ok, reason = _translit_candidate_is_safe(raw_title, query_title, result)
        if not ok:
            return {
                "status": "unverified",
                "query_title": query_title,
                "language": result.get("language", "en-US"),
                "attempt": attempt,
                "attempts": result.get("attempts", 0),
                "confidence": result.get("confidence", 0),
                "rejected_imdb_id": result.get("imdb_id", ""),
                "rejected_tmdb_title": result.get("title", ""),
                "quality_reason": reason,
            }

    if attempt.startswith("series-root"):
        ok, reason = _series_root_is_safe(raw_title, query_title)
        if not ok:
            return {
                "status": "unverified",
                "query_title": query_title,
                "language": result.get("language", "ru-RU"),
                "attempt": attempt,
                "attempts": result.get("attempts", 0),
                "confidence": result.get("confidence", 0),
                "rejected_imdb_id": result.get("imdb_id", ""),
                "rejected_tmdb_title": result.get("title", ""),
                "quality_reason": reason,
            }

    return result


# Install wrappers once.
if me._sanitize_cache_entry is not _sanitize_cache_entry_v11:
    me._sanitize_cache_entry = _sanitize_cache_entry_v11
if me._tmdb_lookup_imdb is not _tmdb_lookup_imdb_v11:
    me._tmdb_lookup_imdb = _tmdb_lookup_imdb_v11

# Backward-compatible test/API alias retained from v9.1/v10.
_sanitize_cache_entry_v91 = _sanitize_cache_entry_v11
