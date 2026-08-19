"""v9.1 precision guards for metadata enrichment.

Loaded by run.py before src.builder. It tightens v9.0 identity matching:
- unsafe transliteration matches are quarantined;
- sequel/part numbers must survive transliteration;
- dotted series subtitles are preserved by default;
- legacy found-cache rows without confidence are revalidated.

Precision first: a missed rating is preferable to a wrong IMDb identity.
"""
from __future__ import annotations

import re

from . import metadata_enrichment as me
from .utils import normalize_name

PATCH_VERSION = "10.0"

me.METADATA_VERSION = PATCH_VERSION
me.CACHE_SCHEMA = 11

_ORIG_LOOKUP = me._tmdb_lookup_imdb
_ORIG_SANITIZE = me._sanitize_cache_entry

_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,3})(?!\d)")


def _significant_numbers(text: str) -> tuple[str, ...]:
    out = []
    for token in _NUMBER_RE.findall(text or ""):
        try:
            n = int(token)
        except ValueError:
            continue
        if 1900 <= n <= 2099:
            continue
        out.append(str(n))
    return tuple(out)


def _translit_candidate_is_safe(raw_title: str, query_title: str, result: dict) -> tuple[bool, str]:
    original_clean = me._clean_search_title(raw_title or "")
    expected_translit = me._transliterate_ru(original_clean)

    # Check raw provider title before confidence/similarity checks. The generic
    # cleaner may strip trailing episode markers and, in strings like
    # ``Лютый 2. 1 с.``, can also erase the sequel number before we inspect it.
    raw_for_numbers = re.sub(
        r"(?i)^\s*(?:х/ф|м/ф|т/с|д/с|д/ф|сериал|фильм|кино)\s*[:.\-–—]?\s*",
        "",
        raw_title or "",
    )
    raw_for_numbers = re.sub(r"\s*[\[(]\s*\d{1,2}\+\s*[\])]\s*", " ", raw_for_numbers)
    original_numbers = _significant_numbers(raw_for_numbers)
    query_numbers = _significant_numbers(query_title)
    if original_numbers and not set(original_numbers).issubset(set(query_numbers)):
        return False, "translit_lost_significant_number"

    candidate_names = [
        str(result.get("title") or ""),
        str(result.get("original_title") or ""),
    ]
    candidate_names = [x for x in candidate_names if x]
    if not candidate_names:
        return False, "translit_missing_candidate_title"

    sims = [me._title_similarity(expected_translit, name) for name in candidate_names]
    best = max(sims, default=0.0)
    if best < 0.93:
        return False, f"translit_candidate_diverged:{best:.3f}"

    confidence = int(result.get("confidence") or 0)
    if confidence < 96:
        return False, f"translit_low_confidence:{confidence}"

    return True, ""


def _series_root_is_safe(raw_title: str, query_title: str) -> tuple[bool, str]:
    cleaned = me._clean_search_title(raw_title or "")
    if ". " not in cleaned:
        return True, ""

    root, suffix = cleaned.split(". ", 1)
    suffix = suffix.strip()

    # Known provider pattern: location after the series root.
    if normalize_name(root) == normalize_name("Наш спецназ") and suffix:
        return True, ""

    # Pure numeric episode/season fragments are safe to collapse.
    if re.fullmatch(r"(?i)(?:сезон\s*)?\d+(?:\s*[сc])?\.?", suffix):
        return True, ""

    return False, "series_root_preserved_subtitle"


def _sanitize_cache_entry_v91(value: dict) -> dict:
    out = _ORIG_SANITIZE(value)
    if out.get("status") == "found":
        reason = ""
        if not str(out.get("confidence") or "").strip():
            reason = "missing_confidence_revalidate_v10"
        elif "genre_ids" not in out or "overview" not in out:
            # v10 needs display metadata in the title cache. Force one clean TMDb refresh
            # for older positive cache rows so genres/overview are actually available to UHF.
            reason = "missing_genre_overview_revalidate_v10"
        if reason:
            return {
                "status": "legacy_unscored",
                "resolver": "tmdb",
                "cached_at": "",
                "miss_count": 0,
                "legacy_imdb_id": str(out.get("imdb_id") or ""),
                "legacy_reason": reason,
            }
    return out


def _tmdb_lookup_imdb_v91(*args, **kwargs) -> dict:
    result = _ORIG_LOOKUP(*args, **kwargs)
    if result.get("status") != "found":
        return result

    attempt = str(result.get("attempt") or "")
    raw_title = str(kwargs.get("raw_title") or (args[6] if len(args) > 6 else ""))
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


me._sanitize_cache_entry = _sanitize_cache_entry_v91
me._tmdb_lookup_imdb = _tmdb_lookup_imdb_v91
