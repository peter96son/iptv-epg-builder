"""v13.18: make compact UHF movie titles idempotent.

Fixes titles such as:
- "Вечера ... (1961) (1961) · IMDb 7.4"
- "Морозко 1965 (1965) · IMDb 6.4"

The patch is loaded before src.builder and replaces only the compact title formatter.
"""
from __future__ import annotations

import re

from . import metadata_enrichment as me

PATCH_VERSION = "13.18-title-normalization"

_IMDB_SUFFIX_RE = re.compile(
    r"\s*[·•]\s*IMDb\s*(?P<rating>(?:10(?:[.,]0)?|[0-9](?:[.,][0-9])?))"
    r"(?:\s*/\s*10)?\s*$",
    re.I,
)


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
    """Return (base, already_has_legitimate_year_suffix).

    Numeric titles such as "1984 (1984)" are preserved: the first 1984 is the
    actual title, so we keep the existing parenthesized production year.
    """
    value = str(value or "").strip()
    if not year:
        return value, False

    pat = _year_suffix_re(year)
    removed = False
    while True:
        m = pat.search(value)
        if not m:
            break
        remainder = value[:m.start()].strip(" -–—,.")
        if not remainder:
            break
        # "1984 (1984)" -> do not turn into "(1984)" or duplicate it.
        if re.fullmatch(rf"{re.escape(year)}", remainder):
            return value, True
        value = remainder
        removed = True
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
    """Normalize an already-generated title when it has a trailing IMDb marker."""
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    m = _IMDB_SUFFIX_RE.search(text)
    if not m:
        return text

    rating = m.group("rating").replace(",", ".")
    before_rating = text[:m.start()].strip()

    year = ""
    # Prefer the last parenthesized year immediately before the IMDb marker.
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


# Install before src.builder imports the formatter into normal build flow.
me._compact_uhf_title = compact_uhf_title
