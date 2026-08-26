"""Cumulative title/series normalization.

v13.18 kept compact UHF titles idempotent.
v14 adds conservative series recognition and strips provider service labels
BEFORE TMDb/IMDb lookup. This file already existed in the production runtime;
V14 no longer requires src.v14_policy_patch.
"""
from __future__ import annotations

import re

from . import metadata_enrichment as me

PATCH_VERSION = "14.8-cumulative-title-normalization"

_IMDB_SUFFIX_RE = re.compile(
    r"\s*[·•]\s*IMDb\s*(?P<rating>(?:10(?:[.,]0)?|[0-9](?:[.,][0-9])?))"
    r"(?:\s*/\s*10)?\s*$",
    re.I,
)

_SERIES_PREFIX = re.compile(r"(?i)^\s*(?:т\s*/\s*с|сериал|мультсериал)\b")
_EPISODE_SUFFIX = re.compile(
    r"(?ix)(?:[,.;:\-–—]?\s*)"
    r"(?:"
    r"(?:серия|сер\.?|эпизод|episode|ep\.?)\s*\d{1,4}"
    r"|\d{1,4}\s*(?:с|сер\.?|серия)"
    r"|(?:сезон|season)\s*\d{1,3}(?:\s*[,.;:\-–—]?\s*(?:серия|эпизод|episode)\s*\d{1,4})?"
    r"|s\d{1,2}\s*e\d{1,4}"
    r")\s*$"
)
# Provider labels are not part of a work's identity.
_BROADCAST_PREFIX = re.compile(
    r"(?ix)^\s*(?:(?:[хx]\s*[/\.]\s*ф|т\s*[/\.]\s*ф|м\s*[/\.]\s*ф)\s*[:.\-–—]?\s*)+"
)
_KNOWN_PARENT_EPISODE = {"три кота", "простоквашино"}

_ORIG_IS_FICTION = me._is_fiction_candidate
_ORIG_MEDIA_TYPE = me._media_type
_ORIG_CLEAN_TITLE = me._clean_search_title
_ORIG_CANONICAL = me._canonical_metadata_title


def _parenthetical_known_series(title: str) -> bool:
    value = (title or "").strip()
    m = re.match(r"^(.{3,80}?)\s*\(([^()]{2,120})\)\s*$", value)
    if not m:
        return False
    inside = m.group(2).strip()
    if re.fullmatch(r"(?:19|20)\d{2}", inside):
        return False
    return m.group(1).strip().lower() in _KNOWN_PARENT_EPISODE


def _strip_lookup_prefixes(title: str) -> str:
    raw = (title or "").strip()
    return _BROADCAST_PREFIX.sub("", raw).strip()


def clean_search_title(title: str) -> str:
    raw = _strip_lookup_prefixes(title)
    protected_number = ""
    m_future = re.search(r"(?<!\d)(20\d{2})\s*$", raw)
    if m_future and int(m_future.group(1)) >= 2030:
        protected_number = m_future.group(1)
        raw_for_legacy = raw[:m_future.start(1)] + "ZZTITLEYEARZZ"
    else:
        raw_for_legacy = raw
    x = _ORIG_CLEAN_TITLE(raw_for_legacy)
    if protected_number:
        x = x.replace("ZZTITLEYEARZZ", protected_number)
    x = re.sub(r"\s*\(\s*(?:19|20)\d{2}\s*\)\s*$", "", x).strip()
    x = re.sub(r"(?i)^\s*(?:т\s*/\s*с|сериал|мультсериал)\s*[:.\-–—]?\s*", "", x).strip()
    x = _EPISODE_SUFFIX.sub("", x).strip(" -–—:;,.")
    if _parenthetical_known_series(raw):
        x = raw.split("(", 1)[0].strip(" -–—:;,.")
    return re.sub(r"\s+", " ", x).strip() or raw


def is_fiction_candidate(programme, group):
    title = me._text(programme, "title").strip()
    if _SERIES_PREFIX.search(title) or _EPISODE_SUFFIX.search(title) or _parenthetical_known_series(title):
        return True
    return _ORIG_IS_FICTION(programme, group)


def media_type(programme, group):
    title = me._text(programme, "title").strip()
    if _SERIES_PREFIX.search(title) or _EPISODE_SUFFIX.search(title) or _parenthetical_known_series(title):
        return "series"
    return _ORIG_MEDIA_TYPE(programme, group)


def canonical_metadata_title(title: str, media_type_name: str) -> str:
    base = clean_search_title(title)
    if media_type_name == "series" and _parenthetical_known_series(_strip_lookup_prefixes(title)):
        return base
    return _ORIG_CANONICAL(base, media_type_name)


def _year_suffix_re(year: str) -> re.Pattern:
    return re.compile(
        rf"\s*(?:\(\s*{re.escape(year)}\s*\)|"
        rf"(?<!\d){re.escape(year)}(?:\s*г(?:од)?\.?)?)\s*$",
        re.I,
    )


def _strip_trailing_imdb(value: str) -> str:
    value = str(value or "").strip()
    while True:
        m = _IMDB_SUFFIX_RE.search(value)
        if not m:
            return value
        value = value[:m.start()].strip()


def _strip_same_year_suffixes(value: str, year: str) -> tuple[str, bool]:
    value = str(value or "").strip()
    if not year:
        return value, False
    pat = _year_suffix_re(year)
    while True:
        m = pat.search(value)
        if not m:
            break
        remainder = value[:m.start()].strip(" -–—,.")
        if not remainder:
            break
        if re.fullmatch(rf"{re.escape(year)}", remainder):
            return value, True
        value = remainder
    return value, False


def compact_uhf_title(title: str, year: str = "", rating: str = "") -> str:
    value = me._strip_programme_prefix(title)
    value = _strip_trailing_imdb(value)
    year_match = me.YEAR_RE.search(str(year or ""))
    clean_year = year_match.group(1) if year_match else ""
    value, year_already_present = _strip_same_year_suffixes(value, clean_year)
    if clean_year and not year_already_present:
        value = f"{value} ({clean_year})".strip()
    clean_rating = str(rating or "").strip().replace(",", ".")
    if clean_rating:
        value = f"{value} · IMDb {clean_rating}".strip()
    return re.sub(r"\s+", " ", value).strip()


def normalize_existing_compact_title(title: str) -> str:
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    m = _IMDB_SUFFIX_RE.search(text)
    if not m:
        return text
    rating = m.group("rating").replace(",", ".")
    before_rating = text[:m.start()].strip()
    year = ""
    m_year = re.search(r"\(\s*((?:19|20)\d{2})\s*\)\s*$", before_rating)
    if m_year:
        year = m_year.group(1)
    else:
        m_year = re.search(r"(?<!\d)((?:19|20)\d{2})(?:\s*г(?:од)?\.?)?\s*$", before_rating, re.I)
        if m_year:
            year = m_year.group(1)
    if not year:
        return text
    return compact_uhf_title(text, year, rating)


# Install before src.builder imports these helpers.
me._compact_uhf_title = compact_uhf_title
me._is_fiction_candidate = is_fiction_candidate
me._media_type = media_type
me._clean_search_title = clean_search_title
me._canonical_metadata_title = canonical_metadata_title
