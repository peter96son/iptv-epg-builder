from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import signal
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .utils import normalize_name
from .metadata_db import MetadataDB, open_metadata_db

TMDB_URL = "https://api.themoviedb.org/3"
METADATA_VERSION = "13.0-stage5"
CACHE_SCHEMA = 9
CACHE_FILE = "metadata-cache.json"
IMDB_ENTITY_CACHE_FILE = "imdb-cache.json"
ALIAS_FILE = "metadata_aliases.json"
IMDB_ENTITY_CACHE_SCHEMA = 2
IMDB_REFRESH_DAYS = 30
IMDB_MISSING_RETRY_DAYS = 7
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
IMDB_BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
IMDB_RATINGS_GZ_FILE = "title.ratings.tsv.gz"
IMDB_BASICS_GZ_FILE = "title.basics.tsv.gz"
IMDB_RATINGS_DB_FILE = "imdb-ratings.sqlite3"
IMDB_LOCAL_DB_FILE = "imdb-local.sqlite3"
IMDB_DATASET_REFRESH_HOURS = 24

IMDB_RATING_RE = re.compile(r"(?i)\bIMDb\b\s*(?:rating|рейтинг)?\s*[:\[\(]?\s*([0-9](?:[\.,][0-9])?|10(?:[\.,]0)?)")
IMDB_ID_RE = re.compile(r"(?i)\b(tt\d{5,12})\b")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
MOVIE_WORDS = {"movie", "movies", "film", "films", "кино", "фильм", "фильмы", "cinema"}
SERIES_WORDS = {"series", "serial", "сериал", "сериалы", "tv series", "episode", "эпизод"}
MOVIE_GROUPS = {"Кино", "Кино 4K", "Кинозалы", "Кинозалы UA"}

TMDB_MOVIE_GENRES_RU = {
    28: "боевик", 12: "приключения", 16: "анимация", 35: "комедия", 80: "криминал",
    99: "документальный", 18: "драма", 10751: "семейный", 14: "фэнтези", 36: "история",
    27: "ужасы", 10402: "музыка", 9648: "детектив", 10749: "мелодрама",
    878: "фантастика", 10770: "телефильм", 53: "триллер", 10752: "военный", 37: "вестерн",
}
TMDB_TV_GENRES_RU = {
    10759: "боевик и приключения", 16: "анимация", 35: "комедия", 80: "криминал",
    99: "документальный", 18: "драма", 10751: "семейный", 10762: "детский",
    9648: "детектив", 10763: "новости", 10764: "реалити", 10765: "фантастика и фэнтези",
    10766: "мыльная опера", 10767: "ток-шоу", 10768: "военный и политика", 37: "вестерн",
}
IMDB_GENRES_RU = {
    "Action": "боевик", "Adventure": "приключения", "Animation": "анимация",
    "Biography": "биография", "Comedy": "комедия", "Crime": "криминал",
    "Documentary": "документальный", "Drama": "драма", "Family": "семейный",
    "Fantasy": "фэнтези", "Film-Noir": "нуар", "Game-Show": "телеигра",
    "History": "история", "Horror": "ужасы", "Music": "музыка",
    "Musical": "мюзикл", "Mystery": "детектив", "News": "новости",
    "Reality-TV": "реалити", "Romance": "мелодрама", "Sci-Fi": "фантастика",
    "Short": "короткометражный", "Sport": "спорт", "Talk-Show": "ток-шоу",
    "Thriller": "триллер", "War": "военный", "Western": "вестерн",
}
DOCUMENTARY_WORDS = {
    "documentary", "documentaries", "doc", "docs", "документальный", "документальные",
    "док", "документалистика", "познавательный", "познавательные", "factual",
}

LANG_MAP = {
    "ru": "ru-RU", "uk": "uk-UA", "ua": "uk-UA", "be": "be-BY", "en": "en-US",
    "de": "de-DE", "pl": "pl-PL", "it": "it-IT", "fr": "fr-FR", "es": "es-ES",
    "pt": "pt-PT", "tr": "tr-TR", "ro": "ro-RO", "bg": "bg-BG", "el": "el-GR",
    "he": "he-IL", "cs": "cs-CZ", "sk": "sk-SK", "hu": "hu-HU", "lt": "lt-LT",
    "lv": "lv-LV", "et": "et-EE", "hr": "hr-HR",
}

# Strong Ukrainian indicators deliberately override an incorrect upstream lang=ru-RU.
UK_STRONG_SUBSTRINGS = (
    "надзвичай", "згадати", "людина", "дівчин", "жінк", "чоловік", "житт", "кохан",
    "війна", "полюван", "вбив", "убивц", "чорн", "черевик", "похован", "голоси",
    "читець", "метелик", "розлютив", "рушниц", "зайц", "мислив", "підозрюван",
    "розплющ", "королів", "крамнич", "індіан", "високий", "дощу", "смертельн",
    "порушивши", "жорсток", "фільм", "мушкетери", "елемент", "миротворець", "прямий",
    "зоряна", "брама", "раптовий", "шпигун", "який", "мене", "кинув", "викликом",
    "п'ятий", "п’ятий", "виродок", "вовченя", "діамант", "весілля", "дівчина",
)
RU_STRONG_SUBSTRINGS = (
    "человек", "девуш", "женщин", "мужчин", "жизн", "любов", "войн", "последн",
    "перв", "истори", "тайн", "убий", "приключ", "город", "мертвец", "бриллиант",
    "рука", "сериал", "след", "условн", "офицер", "штрафник", "свидетел",
)
EN_HINT_RE = re.compile(
    r"(?i)\b(?:the|a|an|and|or|of|to|in|on|for|with|without|after|before|man|woman|girl|"
    r"boy|life|death|love|war|world|new|old|last|first|story|mystery|murder|police|"
    r"adventure|day|night|house|city|road|martian)\b"
)

RU_TRANSLIT = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z",
    "и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
    "с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
    "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
}


def _text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _categories(programme: ET.Element) -> set[str]:
    out: set[str] = set()
    for elem in programme.findall("category"):
        v = normalize_name(elem.text or "")
        if v:
            out.add(v)
    return out


def _programme_year(programme: ET.Element, media_type: str) -> str:
    # XMLTV <date> is trusted. A year embedded in a series schedule title is often an episode plot/year,
    # e.g. "Десантура ... (1995 год)", and must not create a fresh API lookup for each episode.
    date = _text(programme, "date")
    m = YEAR_RE.search(date)
    if m:
        return m.group(1)
    if media_type == "movie":
        m = YEAR_RE.search(_text(programme, "title"))
        if m:
            return m.group(1)
    return ""


def _year(programme: ET.Element) -> str:
    """Backward-compatible helper used by older tests/callers."""
    return _programme_year(programme, _media_type(programme, ""))


def _is_fiction_candidate(programme: ET.Element, group: str) -> bool:
    title = _text(programme, "title").strip().lower()
    joined = " ".join(_categories(programme))
    if re.match(r"^\s*(?:д/с|д/ф)\b", title):
        return False
    if any(word in joined for word in DOCUMENTARY_WORDS):
        return False
    if re.match(r"^\s*(?:х/ф|т/с|сериал|фильм|кино)\b", title):
        return True
    if group in MOVIE_GROUPS:
        return True
    return any(word in joined for word in MOVIE_WORDS | SERIES_WORDS)


def _media_type(programme: ET.Element, group: str) -> str:
    joined = " ".join(_categories(programme))
    title = _text(programme, "title").strip().lower()
    if re.match(r"^\s*(?:д/с|д/ф)\b", title):
        return ""
    if re.match(r"^\s*(?:т/с|сериал)\b", title):
        return "series"
    if re.match(r"^\s*(?:х/ф|фильм|кино)\b", title):
        return "movie"
    if programme.find("episode-num") is not None or any(w in joined for w in SERIES_WORDS):
        return "series"
    if any(w in joined for w in MOVIE_WORDS):
        return "movie"
    if group in MOVIE_GROUPS:
        return "movie"
    return ""


def _existing_imdb(programme: ET.Element):
    desc = _text(programme, "desc")
    rating = ""
    imdb_id = ""
    m = IMDB_RATING_RE.search(desc)
    if m:
        rating = m.group(1).replace(",", ".")
    m = IMDB_ID_RE.search(desc)
    if m:
        imdb_id = m.group(1).lower()
    if not imdb_id:
        for elem in programme.findall("url"):
            m = IMDB_ID_RE.search(elem.text or "")
            if m:
                imdb_id = m.group(1).lower()
                break
    if not rating:
        for elem in programme.findall("rating"):
            if (elem.get("system") or "").strip().lower() == "imdb":
                val = elem.find("value")
                text = (val.text or "").strip() if val is not None else ""
                m = re.search(r"([0-9](?:[\.,][0-9])?|10(?:[\.,]0)?)", text)
                if m:
                    rating = m.group(1).replace(",", ".")
                    break
    return rating, imdb_id


def _genres_for_entry(entry: dict, media_type: str) -> list[str]:
    ids = entry.get("genre_ids") or []
    if isinstance(ids, str):
        ids = [x for x in re.split(r"[,;\s]+", ids) if x]
    mapping = TMDB_MOVIE_GENRES_RU if media_type == "movie" else TMDB_TV_GENRES_RU
    out = []
    for raw in ids:
        try:
            gid = int(raw)
        except (TypeError, ValueError):
            continue
        name = mapping.get(gid)
        if name and name not in out:
            out.append(name)

    # Official IMDb basics genres are English strings. Translate them for the
    # Russian EPG instead of showing "Action, Sci-Fi" on the television.
    for raw in (entry.get("entity_genres") or entry.get("genres") or []):
        value = str(raw or "").strip()
        if not value:
            continue
        name = IMDB_GENRES_RU.get(value, value.lower() if value.isascii() else value)
        if name and name not in out:
            out.append(name)
    return out


def _clean_generated_imdb_suffix(text: str) -> str:
    """Remove metadata lines generated by previous builder versions."""
    value = (text or "").strip()
    if not value:
        return ""

    kept = []
    for line in value.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if re.match(r"(?i)^Жанр(?:ы)?\s*:", clean):
            continue
        if re.match(r"(?i)^IMDb\s*[0-9]+(?:[.,][0-9]+)?/10", clean):
            continue
        if re.match(r"(?i)^(?:Год|Хронометраж|Продолжительность|Оригинальное название)\s*:", clean):
            continue
        if re.match(r"^\d{4}(?:\s*[·•]\s*\d+\s*мин(?:\.)?)?(?:\s*[·•].*)?$", clean):
            continue
        # Technical IMDb IDs from very old generated descriptions are never
        # useful to a viewer.
        if re.fullmatch(r"(?i)tt\d{5,12}", clean):
            continue
        kept.append(clean)

    value = "\n".join(kept).strip()
    value = re.sub(
        r"(?is)\s*(?:•\s*)?IMDb\s*[0-9]+(?:[.,][0-9]+)?/10"
        r"(?:\s*[·•]\s*[\d\s,]+\s*(?:votes|голос(?:ов|а)?))?"
        r"(?:\s*[·•]\s*tt\d{5,12})?\s*$",
        "", value,
    ).strip()
    return value


def _format_votes(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return f"{int(digits):,}".replace(",", " ")


def _normalize_runtime(value) -> int | None:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    return minutes if 1 <= minutes <= 1000 else None


def _normalize_country_names(values) -> list[str]:
    if isinstance(values, str):
        values = [x.strip() for x in re.split(r"[,;/]", values) if x.strip()]
    out = []
    country_map = {
        "US": "США", "USA": "США", "United States of America": "США",
        "United States": "США", "GB": "Великобритания", "UK": "Великобритания",
        "United Kingdom": "Великобритания", "RU": "Россия", "Russia": "Россия",
        "FR": "Франция", "France": "Франция", "DE": "Германия", "Germany": "Германия",
        "IT": "Италия", "Italy": "Италия", "ES": "Испания", "Spain": "Испания",
        "CA": "Канада", "Canada": "Канада", "AU": "Австралия", "Australia": "Австралия",
        "JP": "Япония", "Japan": "Япония", "KR": "Южная Корея", "South Korea": "Южная Корея",
        "IN": "Индия", "India": "Индия", "CN": "Китай", "China": "Китай",
    }
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        text = country_map.get(text, text)
        if text not in out:
            out.append(text)
    return out


def _choose_description(existing: str, overview: str) -> str:
    """Prefer real provider prose, but replace tiny technical stubs with overview."""
    base = _clean_generated_imdb_suffix(existing)
    overview = re.sub(r"\s+", " ", str(overview or "")).strip()
    if not base:
        return overview

    normalized = normalize_name(base)
    technical = bool(re.fullmatch(
        r"(?i)(?:х ф|т с|фильм|сериал|кино|movie|film|series|hd|uhd|4k)(?:\s+\d+)?",
        normalized,
    ))
    if technical or (len(base) < 45 and len(overview) >= max(80, len(base) * 2)):
        return overview
    return base


def _set_single_text_child(programme: ET.Element, tag: str, text: str, attrs: dict | None = None) -> bool:
    text = str(text or "").strip()
    if not text:
        return False
    elem = programme.find(tag)
    if elem is None:
        elem = ET.Element(tag, attrs or {})
        elem.text = text
        programme.append(elem)
        return True
    changed = False
    if (elem.text or "").strip() != text:
        elem.text = text
        changed = True
    for key, value in (attrs or {}).items():
        if elem.get(key) != value:
            elem.set(key, value)
            changed = True
    return changed


def _add_metadata(
    programme: ET.Element, rating: str, imdb_id: str, imdb_votes: str = "",
    overview: str = "", genres: list[str] | None = None,
    *, year: str = "", runtime_minutes=None, countries=None,
    original_title: str = "", display_title: str = "",
) -> bool:
    """Render viewer-facing rich metadata while keeping XMLTV machine fields."""
    changed = False
    rating = (rating or "").strip()
    imdb_id = (imdb_id or "").strip().lower()
    imdb_votes = (imdb_votes or "").strip()
    overview = re.sub(r"\s+", " ", (overview or "").strip())
    genres = [g.strip() for g in (genres or []) if g and g.strip()]
    countries = _normalize_country_names(countries)
    runtime = _normalize_runtime(runtime_minutes)
    year_match = YEAR_RE.search(str(year or ""))
    year = year_match.group(1) if year_match else ""

    if rating and not any((r.get("system") or "").lower() == "imdb" for r in programme.findall("rating")):
        r = ET.Element("rating", {"system": "IMDb"})
        ET.SubElement(r, "value").text = f"{rating}/10"
        programme.append(r)
        changed = True

    # Keep the URL as a machine-readable XMLTV field, never in the visible desc.
    if imdb_id and not any("imdb.com/title/" in (u.text or "").lower() for u in programme.findall("url")):
        u = ET.Element("url")
        u.text = f"https://www.imdb.com/title/{imdb_id}/"
        programme.append(u)
        changed = True

    existing_categories = {normalize_name((c.text or "")) for c in programme.findall("category")}
    for genre in genres:
        if normalize_name(genre) in existing_categories:
            continue
        c = ET.Element("category", {"lang": "ru"})
        c.text = genre
        programme.append(c)
        existing_categories.add(normalize_name(genre))
        changed = True

    # Standard XMLTV fields help clients that support structured metadata.
    if year and not _text(programme, "date"):
        changed |= _set_single_text_child(programme, "date", year)
    if runtime:
        length = programme.find("length")
        if length is None:
            length = ET.Element("length", {"units": "minutes"})
            length.text = str(runtime)
            programme.append(length)
            changed = True
        elif (length.text or "").strip() != str(runtime) or length.get("units") != "minutes":
            length.text = str(runtime)
            length.set("units", "minutes")
            changed = True
    if countries:
        existing_country = {(x.text or "").strip() for x in programme.findall("country")}
        for country in countries:
            if country not in existing_country:
                c = ET.Element("country", {"lang": "ru"})
                c.text = country
                programme.append(c)
                existing_country.add(country)
                changed = True

    desc = programme.find("desc")
    existing = (desc.text or "").strip() if desc is not None else ""
    body = _choose_description(existing, overview)

    lines = []
    facts = []
    if year:
        facts.append(year)
    if runtime:
        facts.append(f"{runtime} мин")
    if countries:
        facts.append(", ".join(countries[:3]))
    if facts:
        lines.append(" · ".join(facts))

    if genres:
        lines.append("Жанр: " + ", ".join(genres) + ".")

    original_title = re.sub(r"\s+", " ", str(original_title or "")).strip()
    visible_title = normalize_name(display_title or _text(programme, "title"))
    if original_title and normalize_name(original_title) and normalize_name(original_title) != visible_title:
        lines.append("Оригинальное название: " + original_title + ".")

    if body:
        lines.append(body)

    if rating:
        rating_line = f"IMDb {rating}/10"
        pretty_votes = _format_votes(imdb_votes)
        if pretty_votes:
            rating_line += f" · {pretty_votes} голосов"
        lines.append(rating_line)

    if lines:
        rendered = "\n".join(lines)
        if desc is None:
            desc = ET.Element("desc", {"lang": "ru"})
            programme.append(desc)
        if (desc.text or "").strip() != rendered:
            desc.text = rendered
            changed = True
    return changed


def _programme_language(programme: ET.Element, title: str) -> str:
    e = programme.find("title")
    lang = (e.get("lang") or "").strip().lower() if e is not None else ""
    if lang:
        return LANG_MAP.get(lang.split("-")[0], lang)
    t = title or ""
    if any(ch in t.lower() for ch in "іїєґ"):
        return "uk-UA"
    cyr = sum(1 for c in t if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in t if c.isascii() and c.isalpha())
    return "ru-RU" if cyr > lat and cyr else "en-US"


def _detect_metadata_language(title: str, provider_lang: str = "") -> str:
    text = (title or "").strip()
    low = text.lower()
    if any(ch in low for ch in "іїєґ"):
        return "uk"
    if "ў" in low:
        return "be"
    if any(stem in low for stem in UK_STRONG_SUBSTRINGS):
        return "uk"

    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    cyr = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    if latin >= 3 and latin > cyr * 2:
        return "en"
    if any(stem in low for stem in RU_STRONG_SUBSTRINGS) or re.search(r"[ыэъё]", low):
        return "ru"
    if EN_HINT_RE.search(low):
        return "en"

    p = (provider_lang or "").lower().split("-")[0]
    if p in {"ru", "en", "uk", "be"}:
        return p
    return "unknown"


def _skip_metadata_language(provider_lang: str, title: str = "") -> bool:
    return _detect_metadata_language(title, provider_lang) not in {"ru", "en"}


def _clean_search_title(title: str) -> str:
    raw = (title or "").strip()
    is_series = bool(re.match(r"(?i)^\s*(?:т/с|д/с|сериал)\b", raw))
    x = re.sub(r"(?i)^\s*(?:х/ф|м/ф|т/с|д/с|д/ф|сериал|фильм|кино)\s*[:.\-–—]?\s*", "", raw)
    x = re.sub(r"\s*[\[(]\s*\d{1,2}\+\s*[\])]\s*", " ", x)
    x = re.sub(r"\s*[\[(]?\s*(?:19\d{2}|20\d{2})\s*(?:год)?\s*[\])]?\s*[.]?\s*$", "", x, flags=re.I)
    x = re.sub(r"(?i)[,.;:]?\s*\d+\s*(?:и|і|&|and|-|–|—)\s*\d+\s*[сc]\.?(?:\s*$)", "", x)
    x = re.sub(r"(?i)[,.;:]?\s*\d+\s*[сc]\.?(?:\s*$)", "", x)
    x = re.sub(r"(?i)\s+(?:серия|сер\.|эпизод|episode)\s*\d+\b.*$", "", x)
    if is_series:
        x = re.sub(r"\s+\d+\.?\s*$", "", x)
    return re.sub(r"\s+", " ", x).strip(" -–—:;,.") or raw


def _effective_metadata_type(raw_title: str, media_type: str) -> str:
    raw = raw_title or ""
    if media_type == "movie" and (
        re.search(r"(?i)\b\d+\s*[сc]\.?(?:\s*$)", raw)
        or re.search(r"(?i)\b\d+\s*(?:и|і|&|and|-|–|—)\s*\d+\s*[сc]\.?(?:\s*$)", raw)
    ):
        return "series"
    return media_type


def _canonical_metadata_title(title: str, media_type: str) -> str:
    base = _clean_search_title(title)
    if media_type == "series":
        # Parenthesized episode titles should not create a new API lookup for every episode.
        base = re.sub(r"\s*\([^()]{1,180}\)\s*$", "", base).strip()
        base = re.sub(r"\s+", " ", base).strip(" -–—:;,.")
    return base or _clean_search_title(title)


def _series_root_fallback(title: str) -> str:
    t = (title or "").strip()
    if ". " in t:
        root = t.split(". ", 1)[0].strip()
        if len(normalize_name(root)) >= 4:
            return root
    return t


def _skip_generic_metadata_title(title: str) -> bool:
    raw = (title or "").strip()
    low = raw.lower()
    if any(low.startswith(prefix) for prefix in (
        "в приближении", "крупным планом", "показ класичних фільмів",
        "показ драматичних фільмів", "світові шедеври кіномистецтва",
    )):
        return True
    return bool(re.match(r"(?i)^\s*spotlight\s*[,.:;-]?\s*\d+\s*[сc]\.?(?:\s*$)", raw))


def _transliterate_ru(text: str) -> str:
    out = []
    for ch in text or "":
        repl = RU_TRANSLIT.get(ch.lower())
        if repl is None:
            out.append(ch)
        elif ch.isupper() and repl:
            out.append(repl[0].upper() + repl[1:])
        else:
            out.append(repl)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _title_variants(title: str) -> list[str]:
    """Conservative variants for provider schedule noise."""
    base = (title or "").strip()
    variants: list[str] = []

    def add(value: str):
        value = re.sub(r"\s+", " ", value or "").strip(' -–—:;,."')
        if value and value not in variants:
            variants.append(value)

    add(base)
    add(base.replace("ё", "е").replace("Ё", "Е"))
    add(re.sub(r'[«»„“”"]', "", base))
    add(re.sub(r"\s*[-–—]\s*", " ", base))

    # Remove only clear schedule decorations; keep sequel numbers such as "Лютый 2".
    add(re.sub(r"(?i)\s*[,:.-]?\s*(?:сезон\s*\d+|\d+\s*сезон)\s*$", "", base))
    add(re.sub(r"(?i)\s*[,:.-]?\s*(?:часть|ч\.)\s*\d+\s*$", "", base))
    add(re.sub(
        r"(?i)\s*[\[(](?:часть|ч\.|серия|сер\.|эпизод|episode)\s*\d+[^\])]*[\])]\s*$",
        "", base
    ))

    translit = _transliterate_ru(base)
    if translit and normalize_name(translit) != normalize_name(base):
        add(translit)
    return variants


def _load_metadata_aliases(root: Path) -> dict[str, list[str]]:
    """Load curated title aliases without guessing translations.

    Format: {"aliases": {"Canonical title": ["Alias 1", "Alias 2"]}}.
    Aliases are search hints only; normal candidate confidence checks still apply.
    """
    path = root / "data" / ALIAS_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    source = raw.get("aliases", raw) if isinstance(raw, dict) else {}
    out: dict[str, list[str]] = {}
    if not isinstance(source, dict):
        return out
    for key, values in source.items():
        canonical = str(key or "").strip()
        if not canonical:
            continue
        vals = values if isinstance(values, list) else [values]
        clean = []
        for value in vals:
            alias = str(value or "").strip()
            if alias and normalize_name(alias) != normalize_name(canonical) and alias not in clean:
                clean.append(alias)
        if clean:
            out[normalize_name(canonical)] = clean
    return out


def _alias_variants(title: str, aliases: dict[str, list[str]]) -> list[str]:
    return aliases.get(normalize_name(title), [])


def _confidence_from_candidate(similarity: float, query_title: str, candidate_title: str, year: str, candidate_year: str, attempt: str) -> int:
    exact = normalize_name(query_title) == normalize_name(candidate_title)
    year_match = bool(year and candidate_year and abs(int(year) - int(candidate_year)) <= 1)
    if exact and year_match:
        score = 100
    elif exact:
        score = 98
    elif similarity >= 0.95 and year_match:
        score = 97
    elif similarity >= 0.95:
        score = 95
    elif similarity >= 0.90:
        score = 92
    elif similarity >= 0.84:
        score = 88
    else:
        score = 84
    if "cross-type" in attempt:
        score -= 3
    if "translit" in attempt:
        score -= 1
    if "alias" in attempt:
        score -= 1
    return max(0, min(100, score))


def _candidate_threshold(title: str, year: str) -> float:
    """Ambiguous short/generic titles need stricter matching."""
    words = normalize_name(title).split()
    if len(words) <= 1 and not year:
        return 0.92
    if len(normalize_name(title)) <= 5 and not year:
        return 0.90
    return 0.82


def _sanitize_cache_entry(value: dict) -> dict:
    out = dict(value or {})
    status = out.get("status")
    iid = str(out.get("imdb_id") or "").strip().lower()
    if status == "found" and IMDB_ID_RE.fullmatch(iid):
        out["imdb_id"] = iid
        # v9 never reports legacy OMDb/direct-page resolvers. Identity came from TMDb.
        out["resolver"] = "tmdb"
        out.pop("rating_source", None)
        # Ratings are entity data and are refreshed from the official IMDb contributor dataset.
        out.pop("imdb_rating", None)
        out.pop("imdb_votes", None)
        out.pop("rating_checked_at", None)
    return out


def _load_cache(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
        entries = raw["entries"]
        schema = int(raw.get("schema") or 0)
        preserve_negatives = schema >= 8
        out = {}
        for k, v in entries.items():
            if not isinstance(v, dict):
                continue
            if v.get("status") == "found":
                iid = str(v.get("imdb_id") or "").strip().lower()
                if IMDB_ID_RE.fullmatch(iid):
                    out[k] = _sanitize_cache_entry(v)
            elif preserve_negatives:
                out[k] = _sanitize_cache_entry(v)
        return out

    # Legacy plain dicts are treated conservatively: migrate positive IDs only.
    if isinstance(raw, dict):
        out = {}
        for k, v in raw.items():
            if not isinstance(v, dict) or v.get("status") != "found":
                continue
            iid = str(v.get("imdb_id") or "").strip().lower()
            if IMDB_ID_RE.fullmatch(iid):
                out[k] = _sanitize_cache_entry(v)
        return out
    return {}


def _save_cache(path: Path, cache: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {"schema": CACHE_SCHEMA, "version": METADATA_VERSION, "saved_at": datetime.now(timezone.utc).isoformat(), "entries": cache}
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _cache_key(title: str, year: str, media_type: str, language: str) -> str:
    return "|".join((normalize_name(title), year or "", media_type or "", language or ""))


def _title_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    scores = [SequenceMatcher(None, na, nb).ratio()]
    # TMDb/IMDb may index a Russian original under Latin transliteration (e.g. Kupel dyavola).
    # Compare transliterated forms too so a valid search hit is not rejected merely because the
    # API returns the Cyrillic display title.
    ta = normalize_name(_transliterate_ru(a))
    tb = normalize_name(_transliterate_ru(b))
    if ta and tb:
        scores.append(SequenceMatcher(None, ta, tb).ratio())
    return max(scores)


@dataclass
class _Budget:
    limit: int
    used: int = 0

    def allow(self) -> bool:
        return self.used < self.limit

    def consume(self) -> bool:
        if not self.allow():
            return False
        self.used += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def _http_json(url: str, timeout: int, headers=None, attempts: int = 3):
    """Fetch JSON with short, bounded retries.

    v11.1 deliberately avoids long retry cascades on GitHub Actions. 429 uses
    Retry-After when it is small; other failures use a short exponential delay.
    """
    req_headers = headers or {"User-Agent": "IPTV-EPG-Builder/11.1"}
    last_exc = None
    for attempt in range(max(1, attempts)):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            delay = min(1.5, 0.25 * (2 ** attempt))
            retry_after = None
            try:
                retry_after = exc.headers.get("Retry-After")
            except Exception:
                pass
            if retry_after:
                try:
                    delay = min(3.0, max(delay, float(retry_after)))
                except (TypeError, ValueError):
                    pass
            time.sleep(delay)
    raise last_exc


def _tmdb_search_multi(api_key: str, title: str, language: str = "en-US", timeout: int = 12):
    p = {"api_key": api_key, "query": title, "include_adult": "false", "language": language}
    return _http_json(f"{TMDB_URL}/search/multi?" + urllib.parse.urlencode(p), timeout)


def _best_tmdb_multi_candidate(payload: dict, title: str, year: str, preferred_type: str):
    best = None
    best_score = 0.0
    for item in (payload.get("results") or [])[:12]:
        media = str(item.get("media_type") or "")
        if media not in {"movie", "tv"}:
            continue
        names = [
            str(item.get("title") or item.get("name") or "").strip(),
            str(item.get("original_title") or item.get("original_name") or "").strip(),
        ]
        sim = max((_title_similarity(title, n) for n in names if n), default=0.0)
        date = str(item.get("release_date") or item.get("first_air_date") or "")
        m = YEAR_RE.search(date)
        cy = m.group(1) if m else ""
        year_ok = not (year and cy) or abs(int(year) - int(cy)) <= 1
        resolved_type = "movie" if media == "movie" else "series"
        score = sim + (0.03 if resolved_type == preferred_type else 0.0)
        if year and cy and year_ok:
            score += 0.08
        threshold = max(0.84, _candidate_threshold(title, year))
        if year_ok and sim >= threshold and score > best_score:
            best = dict(item)
            best["_similarity"] = round(sim, 3)
            best["_candidate_year"] = cy
            best["_resolved_type"] = resolved_type
            best_score = score
    return best


def _tmdb_search(api_key: str, title: str, year: str, media_type: str, language: str = "en-US", timeout: int = 12):
    endpoint = "movie" if media_type == "movie" else "tv"
    p = {"api_key": api_key, "query": title, "include_adult": "false", "language": language}
    if year:
        p["primary_release_year" if media_type == "movie" else "first_air_date_year"] = year
    return _http_json(f"{TMDB_URL}/search/{endpoint}?" + urllib.parse.urlencode(p), timeout)


def _tmdb_external_ids(api_key: str, tmdb_id: int, media_type: str, timeout: int = 12):
    endpoint = "movie" if media_type == "movie" else "tv"
    return _http_json(f"{TMDB_URL}/{endpoint}/{tmdb_id}/external_ids?" + urllib.parse.urlencode({"api_key": api_key}), timeout)


def _tmdb_find_by_imdb_id(api_key: str, imdb_id: str, language: str = "ru-RU", timeout: int = 12) -> dict:
    params = {
        "api_key": api_key,
        "external_source": "imdb_id",
        "language": language,
    }
    payload = _http_json(
        f"{TMDB_URL}/find/{urllib.parse.quote(imdb_id)}?" + urllib.parse.urlencode(params),
        timeout,
    )
    candidates = []
    for media_type, key in (("movie", "movie_results"), ("series", "tv_results")):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                candidates.append((media_type, item))
    if not candidates:
        return {}
    media_type, cand = max(
        candidates,
        key=lambda pair: (
            bool(str(pair[1].get("overview") or "").strip()),
            len(pair[1].get("genre_ids") or []),
            float(pair[1].get("popularity") or 0),
        ),
    )
    return {
        "status": "found",
        "imdb_id": imdb_id,
        "tmdb_id": cand.get("id"),
        "title": cand.get("title") or cand.get("name") or "",
        "original_title": cand.get("original_title") or cand.get("original_name") or "",
        "overview": re.sub(r"\s+", " ", str(cand.get("overview") or "").strip()),
        "genre_ids": list(cand.get("genre_ids") or []),
        "resolved_media_type": media_type,
        "query_title": imdb_id,
        "attempt": "tmdb-find-by-imdb",
        "resolver": "tmdb-find-by-imdb",
        "confidence": 100,
        "language": language,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


def _tmdb_details(api_key: str, tmdb_id: int, media_type: str, language: str = "ru-RU", timeout: int = 12):
    endpoint = "movie" if media_type == "movie" else "tv"
    params = {"api_key": api_key, "language": language}
    return _http_json(f"{TMDB_URL}/{endpoint}/{tmdb_id}?" + urllib.parse.urlencode(params), timeout)


def _best_tmdb_candidate(payload: dict, title: str, year: str, media_type: str):
    best = None
    best_score = 0.0
    for item in (payload.get("results") or [])[:10]:
        names = [
            str(item.get("title") or item.get("name") or "").strip(),
            str(item.get("original_title") or item.get("original_name") or "").strip(),
        ]
        sim = max((_title_similarity(title, n) for n in names if n), default=0.0)
        date = str(item.get("release_date") or item.get("first_air_date") or "")
        m = YEAR_RE.search(date)
        cy = m.group(1) if m else ""
        year_ok = True
        if year and cy:
            year_ok = abs(int(year) - int(cy)) <= 1
        score = sim + (0.08 if year and cy and year_ok else 0.0)
        threshold = _candidate_threshold(title, year)
        if year_ok and sim >= threshold and score > best_score:
            best = dict(item)
            best["_similarity"] = round(sim, 3)
            best["_candidate_year"] = cy
            best_score = score
    return best


def _tmdb_lookup_imdb(
    api_key: str, title: str, year: str, media_type: str, language: str = "en-US",
    timeout: int = 12, raw_title: str = "", budget: _Budget | None = None,
    aliases: dict[str, list[str]] | None = None,
) -> dict:
    cleaned = _canonical_metadata_title(title, media_type)
    attempts: list[tuple] = []
    plans: list[tuple[str, str, str, str, str]] = []

    def add(q, y, lang, typ, label):
        item = (q, y, lang, typ, label)
        if q and item[:4] not in [x[:4] for x in plans]:
            plans.append(item)

    search_variants = _title_variants(cleaned)
    for alias in _alias_variants(cleaned, aliases or {}):
        if alias not in search_variants:
            search_variants.append(alias)

    for variant in search_variants:
        is_translit = normalize_name(variant) != normalize_name(cleaned) and not any("\u0400" <= c <= "\u04ff" for c in variant)
        is_alias = variant in _alias_variants(cleaned, aliases or {})
        label_base = "alias" if is_alias else ("translit" if is_translit else "localized")
        add(variant, year, language if not is_translit else "en-US", media_type, f"{label_base}+year")
        add(variant, "", language if not is_translit else "en-US", media_type, f"{label_base}-no-year")

    if media_type == "series":
        root = _series_root_fallback(cleaned)
        if root and root != cleaned:
            for variant in _title_variants(root):
                lang = "en-US" if not any("\u0400" <= c <= "\u04ff" for c in variant) else language
                add(variant, year, lang, "series", "series-root+year")
                add(variant, "", lang, "series", "series-root-no-year")

    # Provider often labels mini-series as х/ф. Cross-type is safe for multipart rows and as a final fallback.
    other_type = "series" if media_type == "movie" else "movie"
    multipart_hint = bool(
        re.search(r"(?i)\b\d+\s*[сc]\.?(?:\s*$)", raw_title or title)
        or re.search(r"(?i)\b\d+\s*(?:и|і|&|and|-|–|—)\s*\d+\s*[сc]\.?(?:\s*$)", raw_title or title)
    )
    if multipart_hint:
        for variant in _title_variants(cleaned):
            lang = "en-US" if not any("\u0400" <= c <= "\u04ff" for c in variant) else language
            add(variant, year, lang, other_type, "cross-type+year")
            add(variant, "", lang, other_type, "cross-type-no-year")

    no_imdb_candidate = None
    consecutive_empty = 0
    empty_plan_limit = max(2, int(os.environ.get("TMDB_EMPTY_PLAN_LIMIT", "4") or 4))
    for q, y, lang, lookup_type, label in plans:
        # Here budget means actual TMDb HTTP requests, not titles.
        if budget is not None and not budget.consume():
            return {"status": "budget_exhausted", "query_title": cleaned, "language": language, "attempts": len(attempts)}
        attempts.append((q, y, lang, lookup_type))
        payload = _tmdb_search(api_key, q, y, lookup_type, lang, timeout)
        cand = _best_tmdb_candidate(payload, q, y, lookup_type)
        if not cand:
            consecutive_empty += 1
            if consecutive_empty >= empty_plan_limit:
                break
            continue
        consecutive_empty = 0
        tmdb_id = cand.get("id")
        if not tmdb_id:
            continue
        if budget is not None and not budget.consume():
            return {"status": "budget_exhausted", "query_title": q, "language": lang, "attempts": len(attempts)}
        ext = _tmdb_external_ids(api_key, int(tmdb_id), lookup_type, timeout)
        imdb_id = str(ext.get("imdb_id") or "").strip().lower()
        overview = re.sub(r"\s+", " ", str(cand.get("overview") or "").strip())
        genre_ids = list(cand.get("genre_ids") or [])
        if not overview:
            try:
                if budget is None or budget.consume():
                    details = _tmdb_details(api_key, int(tmdb_id), lookup_type, lang, timeout)
                    overview = re.sub(r"\s+", " ", str(details.get("overview") or "").strip())
                    if not genre_ids:
                        genre_ids = [g.get("id") for g in (details.get("genres") or []) if isinstance(g, dict) and g.get("id")]
                if not overview and lang != "en-US" and (budget is None or budget.consume()):
                    details_en = _tmdb_details(api_key, int(tmdb_id), lookup_type, "en-US", timeout)
                    overview = re.sub(r"\s+", " ", str(details_en.get("overview") or "").strip())
                    if not genre_ids:
                        genre_ids = [g.get("id") for g in (details_en.get("genres") or []) if isinstance(g, dict) and g.get("id")]
            except Exception:
                pass
        result = {
            "tmdb_id": tmdb_id,
            "title": cand.get("title") or cand.get("name") or "",
            "original_title": cand.get("original_title") or cand.get("original_name") or "",
            "overview": overview,
            "genre_ids": genre_ids,
            "year": cand.get("_candidate_year", year),
            "similarity": cand.get("_similarity", 0),
            "attempt": label,
            "language": lang,
            "query_title": q,
            "attempts": len(attempts),
            "resolved_media_type": lookup_type,
        }
        candidate_display = result["title"] or result["original_title"]
        result["confidence"] = _confidence_from_candidate(
            float(result.get("similarity") or 0), q, candidate_display, y, str(result.get("year") or ""), label
        )
        if IMDB_ID_RE.fullmatch(imdb_id or ""):
            result.update({"status": "found", "imdb_id": imdb_id})
            return result
        result["status"] = "no_imdb_id"
        no_imdb_candidate = no_imdb_candidate or result
        # Do not stop: another type/variant may have the correct IMDb-linked record.

    if os.environ.get("METADATA_MULTI_FALLBACK", "0").strip().lower() in {"1", "true", "yes"}:
        if cleaned and (budget is None or budget.consume()):
            try:
                payload = _tmdb_search_multi(api_key, cleaned, language, timeout)
                cand = _best_tmdb_multi_candidate(payload, cleaned, year, media_type)
                if cand and cand.get("id"):
                    lookup_type = str(cand.get("_resolved_type") or media_type)
                    tmdb_id = int(cand["id"])
                    if budget is not None and not budget.consume():
                        return {"status": "budget_exhausted", "query_title": cleaned, "language": language, "attempts": len(attempts)}
                    ext = _tmdb_external_ids(api_key, tmdb_id, lookup_type, timeout)
                    imdb_id = str(ext.get("imdb_id") or "").strip().lower()
                    if IMDB_ID_RE.fullmatch(imdb_id):
                        return {
                            "status": "found",
                            "tmdb_id": tmdb_id,
                            "title": cand.get("title") or cand.get("name") or "",
                            "original_title": cand.get("original_title") or cand.get("original_name") or "",
                            "overview": re.sub(r"\s+", " ", str(cand.get("overview") or "").strip()),
                            "genre_ids": list(cand.get("genre_ids") or []),
                            "year": cand.get("_candidate_year", year),
                            "similarity": cand.get("_similarity", 0),
                            "attempt": "multi-fallback",
                            "language": language,
                            "query_title": cleaned,
                            "attempts": len(attempts) + 1,
                            "resolved_media_type": lookup_type,
                            "confidence": _confidence_from_candidate(
                                float(cand.get("_similarity") or 0),
                                cleaned,
                                cand.get("title") or cand.get("name") or "",
                                year,
                                str(cand.get("_candidate_year") or ""),
                                "multi-fallback",
                            ),
                            "imdb_id": imdb_id,
                        }
            except Exception:
                pass

    return no_imdb_candidate or {"status": "not_found", "query_title": cleaned, "language": language, "attempts": len(attempts)}


def _normalize_votes(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(int(value))
    text = str(value).strip().replace(",", "").replace(" ", "")
    return text if text.isdigit() else ""


def _download_atomic(url: str, dest: Path, timeout: int = 90, attempts: int = 3):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    last_exc = None
    for attempt in range(max(1, attempts)):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "IPTV-EPG-Builder/9.0 (personal non-commercial use)",
                    "Accept": "application/gzip, application/octet-stream, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f, length=1024 * 1024)
            if tmp.stat().st_size < 1000:
                raise OSError("IMDb ratings dataset download is unexpectedly small")
            os.replace(tmp, dest)
            return
        except Exception as exc:
            last_exc = exc
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            if attempt + 1 < attempts:
                time.sleep(0.8 * (2 ** attempt))
    raise last_exc


def _dataset_db_age_hours(db_path: Path) -> float | None:
    if not db_path.exists():
        return None
    try:
        return max(0.0, time.time() - db_path.stat().st_mtime) / 3600.0
    except OSError:
        return None


def _imdb_null(value: str) -> str:
    value = str(value or "").strip()
    return "" if value == r"\N" else value


def _build_imdb_local_db(basics_gz: Path, ratings_gz: Path, db_path: Path):
    """Build a local read-only-friendly IMDb SQLite mirror from official bulk files."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(db_path.suffix + ".tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass

    conn = sqlite3.connect(tmp)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("""
            CREATE TABLE basics(
                tconst TEXT PRIMARY KEY,
                title_type TEXT NOT NULL DEFAULT '',
                primary_title TEXT NOT NULL DEFAULT '',
                original_title TEXT NOT NULL DEFAULT '',
                is_adult INTEGER NOT NULL DEFAULT 0,
                start_year TEXT NOT NULL DEFAULT '',
                end_year TEXT NOT NULL DEFAULT '',
                runtime_minutes INTEGER,
                genres TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE ratings(
                tconst TEXT PRIMARY KEY,
                rating TEXT NOT NULL,
                votes INTEGER NOT NULL
            )
        """)

        batch = []
        with gzip.open(basics_gz, "rt", encoding="utf-8", errors="replace", newline="") as f:
            header = f.readline().rstrip("\r\n").split("\t")
            expected = [
                "tconst","titleType","primaryTitle","originalTitle","isAdult",
                "startYear","endYear","runtimeMinutes","genres"
            ]
            if header[:9] != expected:
                raise ValueError(f"Unexpected IMDb basics header: {header[:9]}")
            for line in f:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < 9 or not IMDB_ID_RE.fullmatch(parts[0]):
                    continue
                runtime = _imdb_null(parts[7])
                try:
                    runtime_i = int(runtime) if runtime else None
                except ValueError:
                    runtime_i = None
                batch.append((
                    parts[0],
                    _imdb_null(parts[1]),
                    _imdb_null(parts[2]),
                    _imdb_null(parts[3]),
                    int(parts[4]) if parts[4].isdigit() else 0,
                    _imdb_null(parts[5]),
                    _imdb_null(parts[6]),
                    runtime_i,
                    _imdb_null(parts[8]),
                ))
                if len(batch) >= 50000:
                    conn.executemany(
                        "INSERT OR REPLACE INTO basics VALUES (?,?,?,?,?,?,?,?,?)", batch
                    )
                    batch.clear()
            if batch:
                conn.executemany(
                    "INSERT OR REPLACE INTO basics VALUES (?,?,?,?,?,?,?,?,?)", batch
                )

        batch = []
        with gzip.open(ratings_gz, "rt", encoding="utf-8", errors="replace", newline="") as f:
            header = f.readline().rstrip("\r\n").split("\t")
            if header[:3] != ["tconst","averageRating","numVotes"]:
                raise ValueError(f"Unexpected IMDb ratings header: {header[:3]}")
            for line in f:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) < 3 or not IMDB_ID_RE.fullmatch(parts[0]):
                    continue
                try:
                    votes = int(parts[2])
                except ValueError:
                    continue
                batch.append((parts[0], parts[1], votes))
                if len(batch) >= 50000:
                    conn.executemany("INSERT OR REPLACE INTO ratings VALUES (?,?,?)", batch)
                    batch.clear()
            if batch:
                conn.executemany("INSERT OR REPLACE INTO ratings VALUES (?,?,?)", batch)

        conn.execute("CREATE INDEX basics_title_idx ON basics(primary_title,start_year,title_type)")
        conn.execute("CREATE INDEX basics_original_idx ON basics(original_title,start_year,title_type)")
        conn.execute("CREATE INDEX ratings_votes_idx ON ratings(votes)")
        conn.execute("""
            CREATE VIEW imdb_titles AS
            SELECT b.tconst,b.title_type,b.primary_title,b.original_title,b.is_adult,
                   b.start_year,b.end_year,b.runtime_minutes,b.genres,
                   COALESCE(r.rating,'') AS rating,
                   COALESCE(r.votes,0) AS votes
            FROM basics b
            LEFT JOIN ratings r ON r.tconst=b.tconst
        """)
        conn.execute("PRAGMA user_version=1")
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)


def _prepare_imdb_local_db(root: Path, stats: Counter, timeout: int = 90) -> Path | None:
    cache_dir = root / ".cache" / "imdb"
    db_path = cache_dir / IMDB_LOCAL_DB_FILE
    basics_gz = cache_dir / IMDB_BASICS_GZ_FILE
    ratings_gz = cache_dir / IMDB_RATINGS_GZ_FILE

    age = _dataset_db_age_hours(db_path)
    if age is not None and age < IMDB_DATASET_REFRESH_HOURS:
        stats["imdb_local_dataset_cache_hits"] += 1
        return db_path

    try:
        _download_atomic(IMDB_BASICS_URL, basics_gz, timeout=timeout, attempts=3)
        stats["imdb_basics_downloads"] += 1
        _download_atomic(IMDB_RATINGS_URL, ratings_gz, timeout=timeout, attempts=3)
        stats["imdb_ratings_downloads"] += 1
        _build_imdb_local_db(basics_gz, ratings_gz, db_path)
        stats["imdb_local_dataset_rebuilds"] += 1
        for path in (basics_gz, ratings_gz):
            try:
                path.unlink()
            except OSError:
                pass
        return db_path
    except Exception:
        stats["imdb_local_dataset_errors"] += 1
        if db_path.exists():
            stats["imdb_local_dataset_stale_fallback"] += 1
            return db_path
        return None


def _open_imdb_local_db(db_path: Path | None):
    if not db_path or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn
    except sqlite3.Error:
        return None


def _lookup_imdb_local(conn, imdb_id: str) -> dict:
    if conn is None or not IMDB_ID_RE.fullmatch(imdb_id or ""):
        return {}
    try:
        row = conn.execute(
            """
            SELECT tconst,title_type,primary_title,original_title,is_adult,
                   start_year,end_year,runtime_minutes,genres,rating,votes
            FROM imdb_titles WHERE tconst=?
            """,
            (imdb_id,),
        ).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    return {
        "imdb_id": str(row["tconst"] or ""),
        "title_type": str(row["title_type"] or ""),
        "title": str(row["primary_title"] or ""),
        "original_title": str(row["original_title"] or ""),
        "is_adult": int(row["is_adult"] or 0),
        "year": str(row["start_year"] or ""),
        "end_year": str(row["end_year"] or ""),
        "runtime_minutes": row["runtime_minutes"],
        "genres": [g.strip() for g in str(row["genres"] or "").split(",") if g.strip()],
        "rating": str(row["rating"] or "").strip(),
        "votes": _normalize_votes(row["votes"]),
        "source": "imdb-official-local",
    }


def _imdb_type_to_media_type(title_type: str) -> str:
    t = str(title_type or "").lower()
    if t in {"movie","tvmovie","short","video"}:
        return "movie"
    if t in {"tvseries","tvminiseries","tvshort","tvspecial"}:
        return "series"
    return ""


def _build_imdb_ratings_db(gz_path: Path, db_path: Path):
    """Build a compact local lookup DB from IMDb's official title.ratings.tsv.gz dataset."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(db_path.suffix + ".tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    conn = sqlite3.connect(tmp)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("CREATE TABLE ratings (tconst TEXT PRIMARY KEY, rating TEXT NOT NULL, votes INTEGER NOT NULL)")
        batch = []
        with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace", newline="") as f:
            header = f.readline().rstrip("\n\r").split("\t")
            if header[:3] != ["tconst", "averageRating", "numVotes"]:
                raise ValueError(f"Unexpected IMDb ratings header: {header[:3]}")
            for line in f:
                parts = line.rstrip("\n\r").split("\t")
                if len(parts) < 3 or not IMDB_ID_RE.fullmatch(parts[0]):
                    continue
                try:
                    votes = int(parts[2])
                except ValueError:
                    continue
                batch.append((parts[0], parts[1], votes))
                if len(batch) >= 50000:
                    conn.executemany("INSERT OR REPLACE INTO ratings VALUES (?,?,?)", batch)
                    batch.clear()
            if batch:
                conn.executemany("INSERT OR REPLACE INTO ratings VALUES (?,?,?)", batch)
        conn.execute("CREATE INDEX IF NOT EXISTS ratings_votes_idx ON ratings(votes)")
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)


def _prepare_imdb_ratings_db(root: Path, stats: Counter, timeout: int = 90) -> Path | None:
    cache_dir = root / ".cache" / "imdb"
    db_path = cache_dir / IMDB_RATINGS_DB_FILE
    gz_path = cache_dir / IMDB_RATINGS_GZ_FILE
    age = _dataset_db_age_hours(db_path)
    if age is not None and age < IMDB_DATASET_REFRESH_HOURS:
        stats["imdb_dataset_cache_hits"] += 1
        return db_path

    try:
        _download_atomic(IMDB_RATINGS_URL, gz_path, timeout=timeout, attempts=3)
        stats["imdb_dataset_downloads"] += 1
        _build_imdb_ratings_db(gz_path, db_path)
        stats["imdb_dataset_rebuilds"] += 1
        try:
            gz_path.unlink()
        except OSError:
            pass
        return db_path
    except Exception as exc:
        stats["imdb_dataset_errors"] += 1
        # A stale DB is still better than no ratings at all.
        if db_path.exists():
            stats["imdb_dataset_stale_fallback"] += 1
            return db_path
        return None


def _open_imdb_ratings_db(db_path: Path | None):
    if not db_path or not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
        return conn
    except sqlite3.Error:
        return None


def _lookup_imdb_dataset(conn, imdb_id: str) -> dict:
    if conn is None or not IMDB_ID_RE.fullmatch(imdb_id or ""):
        return {"rating": "", "votes": ""}
    try:
        row = conn.execute("SELECT rating, votes FROM ratings WHERE tconst=?", (imdb_id,)).fetchone()
    except sqlite3.Error:
        return {"rating": "", "votes": ""}
    if not row:
        return {"rating": "", "votes": ""}
    return {"rating": str(row[0] or "").strip(), "votes": _normalize_votes(row[1])}


def _load_imdb_entity_cache(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
        out = {}
        for iid, value in raw["entries"].items():
            iid = str(iid).strip().lower()
            if not IMDB_ID_RE.fullmatch(iid) or not isinstance(value, dict):
                continue
            out[iid] = {
                "rating": str(value.get("rating") or "").strip(),
                "votes": _normalize_votes(value.get("votes")),
                "source": "imdb-dataset" if (value.get("rating") or value.get("votes")) else "",
                "checked_at": str(value.get("checked_at") or ""),
            }
        return out
    return {}


def _save_imdb_entity_cache(path: Path, cache: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "schema": IMDB_ENTITY_CACHE_SCHEMA,
        "version": METADATA_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "entries": cache,
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _imdb_entity_fresh(entity: dict) -> bool:
    if not isinstance(entity, dict):
        return False
    ts = entity.get("checked_at")
    if not ts:
        return False
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except (ValueError, TypeError):
        return False
    has_data = bool(entity.get("rating") or entity.get("votes"))
    days = IMDB_REFRESH_DAYS if has_data else IMDB_MISSING_RETRY_DAYS
    return age < days * 86400


def _resolve_imdb_entity(
    imdb_id: str, entity_cache: dict, stats: Counter, ratings_conn=None,
) -> dict:
    iid = (imdb_id or "").strip().lower()
    if not IMDB_ID_RE.fullmatch(iid):
        return {"rating": "", "votes": "", "source": ""}

    cached = entity_cache.get(iid)
    if cached and _imdb_entity_fresh(cached):
        stats["imdb_entity_cache_hits"] += 1
        return cached

    stats["imdb_dataset_lookups"] += 1
    meta = _lookup_imdb_dataset(ratings_conn, iid)
    rating = str(meta.get("rating") or "").strip()
    votes = _normalize_votes(meta.get("votes"))
    source = "imdb-dataset" if rating or votes else ""
    entity = {
        "rating": rating,
        "votes": votes,
        "source": source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    entity_cache[iid] = entity
    stats["imdb_entity_cache_updates"] += 1
    if rating:
        stats["imdb_rating_matches"] += 1
    if votes:
        stats["imdb_votes_matches"] += 1
    if not rating and not votes:
        stats["imdb_dataset_not_found"] += 1
    return entity


def _negative_cache_fresh(entry: dict) -> bool:
    status = entry.get("status")
    if status == "found":
        return True
    ts = entry.get("cached_at")
    if not ts:
        return False
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except (ValueError, TypeError):
        return False
    misses = max(1, int(entry.get("miss_count") or 1))
    if status == "not_found":
        ttl_days = 2 if misses <= 1 else (7 if misses <= 3 else 30)
    elif status == "no_imdb_id":
        ttl_days = 14 if misses <= 2 else 30
    else:
        ttl_days = 3
    return age < ttl_days * 86400


def _rating_needs_retry(entry: dict) -> bool:
    if entry.get("status") != "found" or entry.get("imdb_rating"):
        return False
    ts = entry.get("rating_checked_at") or entry.get("cached_at")
    if not ts:
        return True
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except (ValueError, TypeError):
        return True
    return age >= 7 * 86400


def enrich_metadata(tv: ET.Element, mappings: list[dict], root: Path, output: Path) -> dict:
    """Enrich fiction programmes using persistent SQLite metadata storage.

    v11 behaviour:
    * `.cache/metadata/metadata.sqlite3` is the authoritative title/entity cache.
    * v10 JSON caches are imported once when the SQLite DB is empty.
    * one budget unit means one previously-unknown canonical title, not one HTTP request.
    * successful high-confidence matches teach aliases for future zero-request resolution.
    * descriptions keep provider text when present, otherwise TMDb overview is used;
      genres and IMDb rating are appended for UHF display.
    """
    tmdb_key = os.environ.get("TMDB_API_KEY", "").strip()
    # Backward-compatible title budget plus a separate hard HTTP budget.
    max_titles = max(0, int(os.environ.get("METADATA_MAX_TITLES", os.environ.get("METADATA_MAX_REQUESTS", "20000")) or 20000))
    max_http_requests = max(0, int(os.environ.get("METADATA_MAX_HTTP_REQUESTS", "2500") or 2500))
    timeout = max(3, int(os.environ.get("METADATA_TIMEOUT", "8") or 8))
    progress_every = max(10, int(os.environ.get("METADATA_PROGRESS_EVERY", "25") or 25))
    checkpoint_every = max(5, int(os.environ.get("METADATA_CHECKPOINT_EVERY", "25") or 25))
    deadline_seconds = max(60, int(os.environ.get("METADATA_DEADLINE_SECONDS", "2100") or 2100))
    metadata_deadline = time.monotonic() + deadline_seconds
    title_budget = _Budget(max_titles)
    http_budget = _Budget(max_http_requests)
    aliases = _load_metadata_aliases(root)

    groups: dict[str, str] = {}
    allowed: set[str] = set()
    for row in mappings:
        oid = (row.get("output_tvg_id") or "").strip()
        if oid:
            allowed.add(oid)
            groups.setdefault(oid, row.get("group", ""))

    stats = Counter()
    rows: list[dict] = []
    ratings_db_path = None
    ratings_conn = None
    local_imdb_db_path = None
    local_imdb_conn = None

    metadata_dir = root / ".cache" / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    legacy_cache_path = metadata_dir / CACHE_FILE
    legacy_imdb_path = metadata_dir / IMDB_ENTITY_CACHE_FILE

    db = open_metadata_db(root)

    # Graceful stop: GitHub Actions sends SIGTERM before force-killing a job.
    # Do not abort in the handler; ask the metadata loop to wind down, checkpoint
    # SQLite, and return a valid EPG/report.
    stop_requested = {"value": False, "reason": ""}
    previous_sigterm = None

    def _request_stop(signum, frame):
        stop_requested["value"] = True
        stop_requested["reason"] = stop_requested["reason"] or "signal"

    try:
        previous_sigterm = signal.signal(signal.SIGTERM, _request_stop)
    except (ValueError, OSError, AttributeError):
        previous_sigterm = None

    # Import the v10 caches only into an empty v11 database. We intentionally
    # run legacy title entries through the current sanitizer so the v9.1/v10
    # precision guard can force questionable rows to be resolved again.
    counts_before = db.counts()
    if counts_before["titles"] == 0 and counts_before["imdb_entities"] == 0:
        legacy_title_cache: dict = {}
        legacy_entity_cache: dict = {}

        candidates = [
            legacy_cache_path,
            metadata_dir / "metadata-v80.json",
            metadata_dir / "metadata-v70.json",
            metadata_dir / "metadata-v60.json",
            metadata_dir / "metadata-v50.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                legacy_title_cache = _load_cache(candidate)
                if legacy_title_cache:
                    break

        entity_candidates = [
            legacy_imdb_path,
            metadata_dir / "imdb-entities-v80.json",
            metadata_dir / "imdb-entities-v70.json",
        ]
        for candidate in entity_candidates:
            if candidate.exists():
                legacy_entity_cache = _load_imdb_entity_cache(candidate)
                if legacy_entity_cache:
                    break

        for key, entry in legacy_title_cache.items():
            parts = str(key).split("|")
            if len(parts) < 4 or not isinstance(entry, dict):
                stats["sqlite_migration_skipped"] += 1
                continue
            _normalized, year, media_type = parts[0], parts[1], parts[2]
            language = "|".join(parts[3:])
            display = str(entry.get("query_title") or entry.get("title") or _normalized)
            db.put_title(display, year, media_type, language, entry)
            stats["sqlite_migrated_titles"] += 1

        for iid, entity in legacy_entity_cache.items():
            if isinstance(entity, dict) and IMDB_ID_RE.fullmatch((iid or "").strip().lower()):
                db.put_imdb_entity(iid, entity)
                stats["sqlite_migrated_entities"] += 1

        if legacy_title_cache or legacy_entity_cache:
            db.conn.commit()

    def ensure_ratings_conn():
        nonlocal ratings_db_path, ratings_conn
        if ratings_conn is not None:
            return ratings_conn
        ratings_db_path = _prepare_imdb_ratings_db(root, stats, timeout=max(60, timeout))
        ratings_conn = _open_imdb_ratings_db(ratings_db_path)
        if ratings_conn is not None:
            stats["imdb_dataset_available"] = 1
            try:
                stats["imdb_dataset_db_bytes"] = int(ratings_db_path.stat().st_size)
            except OSError:
                pass
        return ratings_conn

    def ensure_local_imdb_conn():
        nonlocal local_imdb_db_path, local_imdb_conn
        if local_imdb_conn is not None:
            return local_imdb_conn
        local_imdb_db_path = _prepare_imdb_local_db(
            root, stats, timeout=max(90, timeout)
        )
        local_imdb_conn = _open_imdb_local_db(local_imdb_db_path)
        if local_imdb_conn is not None:
            stats["imdb_local_dataset_available"] = 1
            try:
                stats["imdb_local_dataset_db_bytes"] = int(local_imdb_db_path.stat().st_size)
            except OSError:
                pass
        return local_imdb_conn


    def resolve_entity(iid: str, seed: dict | None = None) -> dict:
        iid = (iid or "").strip().lower()
        if not IMDB_ID_RE.fullmatch(iid):
            return {"rating": "", "votes": "", "source": ""}

        cached = db.get_imdb_entity(iid)

        # Resolver-provided values are authoritative for the current pass and do
        # not require a dataset refresh solely to duplicate rating/votes.
        if seed and (seed.get("imdb_rating") or seed.get("imdb_votes")):
            entity = dict(cached or {})
            entity.update({
                "rating": str(seed.get("imdb_rating") or entity.get("rating") or ""),
                "votes": _normalize_votes(seed.get("imdb_votes") or entity.get("votes")),
                "source": str(seed.get("rating_source") or entity.get("source") or "resolver"),
                "checked_at": str(seed.get("rating_checked_at") or datetime.now(timezone.utc).isoformat()),
            })
        elif cached and _imdb_entity_fresh(cached) and (
            cached.get("runtime_minutes") or cached.get("genres") or cached.get("title")
        ):
            stats["imdb_entity_cache_hits"] += 1
            entity = dict(cached)
        else:
            entity = dict(cached or {})

            # Stage 4: official IMDb bulk mirror first. This is a local SQLite
            # lookup and spends zero per-title HTTP requests.
            conn = ensure_local_imdb_conn()
            local = _lookup_imdb_local(conn, iid)
            if local:
                entity.update({
                    "rating": str(local.get("rating") or entity.get("rating") or ""),
                    "votes": _normalize_votes(local.get("votes") or entity.get("votes")),
                    "source": "imdb-official-local",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "title": str(local.get("title") or entity.get("title") or ""),
                    "original_title": str(local.get("original_title") or entity.get("original_title") or ""),
                    "year": str(local.get("year") or entity.get("year") or ""),
                    "end_year": str(local.get("end_year") or entity.get("end_year") or ""),
                    "runtime_minutes": local.get("runtime_minutes") or entity.get("runtime_minutes"),
                    "genres": list(local.get("genres") or entity.get("genres") or []),
                    "title_type": str(local.get("title_type") or entity.get("title_type") or ""),
                    "media_type": _imdb_type_to_media_type(local.get("title_type")) or entity.get("media_type") or "",
                    "is_adult": int(local.get("is_adult") or 0),
                })
                stats["imdb_local_entity_hits"] += 1
                if local.get("rating"):
                    stats["imdb_rating_matches"] += 1
                if local.get("votes"):
                    stats["imdb_votes_matches"] += 1
                if local.get("runtime_minutes"):
                    stats["imdb_runtime_matches"] += 1
                if local.get("genres"):
                    stats["imdb_genre_matches"] += 1
            else:
                # Compatibility fallback: old ratings-only local DB.
                rconn = ensure_ratings_conn()
                stats["imdb_dataset_lookups"] += 1
                meta = _lookup_imdb_dataset(rconn, iid)
                rating = str(meta.get("rating") or "").strip()
                votes = _normalize_votes(meta.get("votes"))
                entity.update({
                    "rating": rating,
                    "votes": votes,
                    "source": "imdb-dataset" if rating or votes else "",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
                if rating:
                    stats["imdb_rating_matches"] += 1
                if votes:
                    stats["imdb_votes_matches"] += 1
                if not rating and not votes:
                    stats["imdb_dataset_not_found"] += 1

            stats["imdb_entity_cache_updates"] += 1

        # Merge current TMDb identity/display data when available.
        if seed:
            seed_genres = _genres_for_entry(
                seed, str(seed.get("resolved_media_type") or "movie")
            )
            for field, value in (
                ("title", seed.get("title")),
                ("original_title", seed.get("original_title")),
                ("overview", seed.get("overview")),
                ("year", seed.get("candidate_year")),
                ("runtime_minutes", seed.get("runtime_minutes")),
            ):
                if value and not entity.get(field):
                    entity[field] = value
            if seed_genres and not entity.get("genres"):
                entity["genres"] = seed_genres

        db.put_imdb_entity(iid, entity)
        return entity


    # In-run memo guarantees repeated episodes/timeslots use one resolved row.
    memo: dict[str, dict] = {}

    programmes = list(tv.findall("programme"))

    def _metadata_priority(p: ET.Element) -> tuple[int, str]:
        cid = (p.get("channel") or "").strip()
        group = groups.get(cid, "")
        title = _text(p, "title").strip().lower()
        if group in MOVIE_GROUPS:
            return (0, cid)
        if re.match(r"^\s*(?:х/ф|фильм|кино)\b", title):
            return (1, cid)
        if re.match(r"^\s*(?:т/с|сериал)\b", title):
            return (2, cid)
        return (3, cid)

    programmes.sort(key=_metadata_priority)
    total_programmes = len(programmes)
    print(
        f"[metadata] start; programmes={total_programmes}; sqlite={db.path.name}; "
        f"title-budget={max_titles}; http-budget={max_http_requests}; deadline={deadline_seconds}s",
        flush=True,
    )

    for p in programmes:
        if stop_requested["value"]:
            stats["signal_stop"] = 1
            print(
                f"[metadata] stop requested ({stop_requested['reason'] or 'signal'}); "
                f"titles={title_budget.used}; http={http_budget.used}; checkpointing and finishing",
                flush=True,
            )
            break
        if time.monotonic() >= metadata_deadline:
            stats["deadline_reached"] = 1
            stop_requested["reason"] = stop_requested["reason"] or "deadline"
            print(
                f"[metadata] deadline reached; titles={title_budget.used}; http={http_budget.used}; "
                "finishing EPG with cached/collected metadata",
                flush=True,
            )
            break
        cid = (p.get("channel") or "").strip()
        if cid not in allowed:
            continue
        stats["programmes_considered"] += 1
        title = _text(p, "title")
        if not title:
            continue

        rating, iid = _existing_imdb(p)
        if rating or iid:
            stats["programmes_with_existing_imdb"] += 1
            entity = resolve_entity(iid) if iid else {}

            # IMDb ratings dataset has only rating/votes. If identity is already
            # known but display metadata is absent, resolve overview/genres from
            # TMDb directly by IMDb ID instead of fuzzy title search.
            if iid and (
                not list(entity.get("genres") or [])
                or not str(entity.get("overview") or "").strip()
            ):
                if (
                    tmdb_key
                    and http_budget.allow()
                    and time.monotonic() < metadata_deadline
                    and not stop_requested["value"]
                ):
                    try:
                        detected_language = _detect_metadata_language(
                            title, _programme_language(p, title)
                        )
                        lang = "ru-RU" if detected_language == "ru" else "en-US"

                        http_budget.consume()
                        seed = _tmdb_find_by_imdb_id(tmdb_key, iid, lang, timeout)

                        if seed and (
                            not str(seed.get("overview") or "").strip()
                            or not list(seed.get("genre_ids") or [])
                        ) and lang != "en-US" and http_budget.allow():
                            http_budget.consume()
                            seed_en = _tmdb_find_by_imdb_id(tmdb_key, iid, "en-US", timeout)
                            if seed_en:
                                if not str(seed.get("overview") or "").strip():
                                    seed["overview"] = seed_en.get("overview") or ""
                                if not list(seed.get("genre_ids") or []):
                                    seed["genre_ids"] = seed_en.get("genre_ids") or []

                        if seed:
                            entity = resolve_entity(iid, seed=seed)
                            stats["existing_imdb_tmdb_display_refresh"] += 1
                        else:
                            stats["existing_imdb_tmdb_find_not_found"] += 1
                    except Exception:
                        stats["existing_imdb_tmdb_display_refresh_errors"] += 1
                else:
                    stats["existing_imdb_display_refresh_deferred"] += 1

            final_rating = rating or str(entity.get("rating") or "")
            final_votes = _normalize_votes(entity.get("votes"))
            genres = list(entity.get("genres") or [])
            overview = str(entity.get("overview") or "")
            if _add_metadata(
                p, final_rating, iid, final_votes,
                overview=overview, genres=genres,
                year=str(entity.get("year") or _programme_year(p, _media_type(p, groups.get(cid, ""))) or ""),
                runtime_minutes=entity.get("runtime_minutes"),
                countries=entity.get("countries") or [],
                original_title=str(entity.get("original_title") or ""),
                display_title=title,
            ):
                stats["existing_metadata_normalized"] += 1
            continue

        if _skip_generic_metadata_title(title):
            stats["generic_schedule_blocks_skipped"] += 1
            continue
        if not _is_fiction_candidate(p, groups.get(cid, "")):
            stats["non_fiction_skipped"] += 1
            continue

        typ = _media_type(p, groups.get(cid, ""))
        if not typ:
            stats["not_movie_or_series"] += 1
            continue
        if len(normalize_name(title)) < 3:
            stats["title_too_short"] += 1
            continue

        provider_language = _programme_language(p, title)
        detected_language = _detect_metadata_language(title, provider_language)
        if detected_language not in {"ru", "en"}:
            stats["non_ru_en_titles_skipped"] += 1
            stats[f"{detected_language}_titles_skipped"] += 1
            continue
        language = "ru-RU" if detected_language == "ru" else "en-US"

        effective_type = _effective_metadata_type(title, typ)
        canonical_title = _canonical_metadata_title(title, effective_type)
        if normalize_name(canonical_title) != normalize_name(_clean_search_title(title)):
            stats["episode_titles_collapsed"] += 1
        if effective_type != typ:
            stats["multipart_movies_reclassified"] += 1

        year = _programme_year(p, effective_type)
        key = _cache_key(canonical_title, year, effective_type, language)
        entry = memo.get(key)
        source = "memo"

        if entry is not None:
            stats["in_run_memo_hits"] += 1
        else:
            # v13 stage 2: normalized knowledge layer is the primary resolver.
            entry = db.resolve_knowledge(
                canonical_title, year, effective_type, language
            )
            if entry is not None:
                source = str(entry.get("resolver") or "knowledge")
                stats["knowledge_hits"] += 1
                # Keep the old aggregate counter for backward-compatible reports/tests.
                stats["sqlite_title_hits"] += 1
                if source in {"knowledge-alias", "knowledge-smart-alias"}:
                    stats["knowledge_alias_hits"] += 1
                    if source == "knowledge-smart-alias":
                        stats["knowledge_smart_alias_hits"] += 1
                else:
                    stats["knowledge_title_hits"] += 1

            # Legacy cache is compatibility fallback only.
            if entry is None:
                entry = db.get_title(canonical_title, year, effective_type, language)
                if entry is not None and _negative_cache_fresh(entry):
                    source = "sqlite-legacy"
                    stats["sqlite_title_hits"] += 1
                elif entry is not None:
                    stats["sqlite_stale_retried"] += 1
                    entry = None

            # Legacy alias fallback for pre-v13 rows not yet linked by title_id.
            if entry is None:
                alias_row = db.get_alias(canonical_title, year, effective_type)
                if alias_row:
                    alias_iid = str(alias_row.get("imdb_id") or "")
                    entity = db.get_imdb_entity(alias_iid) or {}
                    entry = {
                        "status": "found",
                        "imdb_id": alias_iid,
                        "title": str(entity.get("title") or canonical_title),
                        "original_title": str(entity.get("original_title") or ""),
                        "overview": str(entity.get("overview") or ""),
                        "genre_ids": [],
                        "resolved_media_type": effective_type,
                        "query_title": canonical_title,
                        "attempt": "sqlite-alias-legacy",
                        "resolver": "sqlite-alias-legacy",
                        "confidence": alias_row.get("confidence") or 98,
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                        "entity_genres": list(entity.get("genres") or []),
                    }
                    source = "sqlite-alias-legacy"
                    stats["sqlite_alias_hits"] += 1

            # A verified identity may be complete enough for IMDb but still
            # lack genres/overview. Keep the identity usable immediately and
            # refresh display fields only when budget/time permits.
            display_fallback = None
            if entry is not None and entry.get("status") == "found" and entry.get("needs_display_refresh"):
                if (
                    tmdb_key
                    and title_budget.allow()
                    and http_budget.allow()
                    and time.monotonic() < metadata_deadline
                    and not stop_requested["value"]
                ):
                    display_fallback = dict(entry)
                    display_fallback.pop("needs_display_refresh", None)
                    entry = None
                    source = "display-refresh"
                    stats["display_refresh_attempted"] += 1
                else:
                    stats["display_refresh_deferred"] += 1

            if entry is None:
                if not title_budget.allow() or not http_budget.allow():
                    stats["lookup_not_attempted"] += 1
                    if not http_budget.allow():
                        stats["http_budget_exhausted"] = 1
                    continue
                if not tmdb_key:
                    stats["lookup_not_attempted"] += 1
                    continue
                try:
                    title_budget.consume()
                    entry = _tmdb_lookup_imdb(
                        tmdb_key, canonical_title, year, effective_type, language, timeout,
                        raw_title=title, budget=http_budget, aliases=aliases,
                    )
                    stats["tmdb_resolver_calls"] += 1
                    source = "tmdb"

                    if entry.get("status") == "found":
                        stats["tmdb_matches"] += 1
                        entity = resolve_entity(entry.get("imdb_id", ""), seed=entry)
                        entry["imdb_rating"] = str(entity.get("rating") or "").strip()
                        entry["imdb_votes"] = _normalize_votes(entity.get("votes"))
                        entry["rating_source"] = str(entity.get("source") or "")
                        entry["rating_checked_at"] = str(entity.get("checked_at") or "")
                        entry["resolver"] = "tmdb+imdb-dataset" if entry.get("imdb_rating") or entry.get("imdb_votes") else "tmdb"
                        if str(entry.get("attempt", "")).startswith("alias"):
                            stats["alias_matches"] += 1
                        stats[f"confidence_{entry.get('confidence', 0)}"] += 1
                    else:
                        stats[f"tmdb_{entry.get('status', 'other')}"] += 1
                        entry["resolver"] = "tmdb"
                        entry["miss_count"] = int(entry.get("miss_count") or 0) + 1

                    entry["cached_at"] = datetime.now(timezone.utc).isoformat()
                    if entry.get("status") != "budget_exhausted":
                        db.put_title(canonical_title, year, effective_type, language, entry)
                        stats["sqlite_title_updates"] += 1

                    # Teach only strong positive identities. Translit matches
                    # remain subject to v9.1 quality guards before reaching here.
                    if entry.get("status") == "found" and int(entry.get("confidence") or 0) >= 97:
                        iid_found = str(entry.get("imdb_id") or "")
                        learned_aliases = {
                            canonical_title,
                            _clean_search_title(title),
                            str(entry.get("query_title") or ""),
                            str(entry.get("title") or ""),
                            str(entry.get("original_title") or ""),
                        }
                        learned_count = db.teach_alias_family(
                            [x for x in learned_aliases if x and len(normalize_name(x)) >= 3],
                            iid_found, year, effective_type,
                            source="tmdb-smart-alias",
                            confidence=int(entry.get("confidence") or 0),
                        )
                        stats["sqlite_alias_updates"] += learned_count
                        stats["smart_alias_updates"] += learned_count

                    if title_budget.used % checkpoint_every == 0:
                        db.conn.commit()
                        db.checkpoint()
                        stats["sqlite_periodic_checkpoints"] += 1
                    if title_budget.used % progress_every == 0:
                        counts = db.counts()
                        print(
                            f"[metadata] titles={title_budget.used}/{max_titles}; "
                            f"http={http_budget.used}/{max_http_requests}; "
                            f"matches={stats['tmdb_matches']}; sqlite_hits={stats['sqlite_title_hits']}; "
                            f"aliases={stats['sqlite_alias_hits']}; db_titles={counts['titles']}",
                            flush=True,
                        )
                except Exception as exc:
                    stats["api_errors"] += 1
                    rows.append({
                        "channel_id": cid, "title": title, "year": year, "type": typ, "status": "api_error",
                        "source": "metadata-api", "imdb_id": "", "imdb_rating": "", "imdb_votes": "", "detail": str(exc)[:180],
                    })
                    continue

            # Failed display refresh must never destroy an already-verified IMDb identity.
            if (
                display_fallback is not None
                and (entry is None or entry.get("status") != "found")
            ):
                stats["display_refresh_fallback_used"] += 1
                entry = display_fallback
                source = "sqlite-display-fallback"
                db.put_title(canonical_title, year, effective_type, language, entry)

            if entry and entry.get("status") == "found":
                # Successful refresh is now complete only if both display fields exist.
                if entry.get("needs_display_refresh"):
                    has_genres = bool(entry.get("genre_ids"))
                    has_overview = bool(str(entry.get("overview") or "").strip())
                    if has_genres and has_overview:
                        entry.pop("needs_display_refresh", None)
                        db.put_title(canonical_title, year, effective_type, language, entry)
                        stats["display_refresh_completed"] += 1
                try:
                    entity = resolve_entity(entry.get("imdb_id", ""), seed=entry)
                    entry["imdb_rating"] = str(entity.get("rating") or "").strip()
                    entry["imdb_votes"] = _normalize_votes(entity.get("votes"))
                    entry["rating_source"] = str(entity.get("source") or "")
                    entry["rating_checked_at"] = str(entity.get("checked_at") or "")
                    if source.startswith("sqlite"):
                        entry["resolver"] = source
                    elif entry.get("imdb_rating") or entry.get("imdb_votes"):
                        entry["resolver"] = "tmdb+imdb-dataset"
                    db.put_title(canonical_title, year, effective_type, language, entry)
                except Exception:
                    stats["rating_refresh_errors"] += 1

            memo[key] = entry

        if entry and entry.get("status") == "found":
            rating = str(entry.get("imdb_rating", "")).strip()
            votes = _normalize_votes(entry.get("imdb_votes"))
            iid = str(entry.get("imdb_id", "")).strip()
            entity = db.get_imdb_entity(iid) or {}
            genres = _genres_for_entry(entry, effective_type)
            if not genres:
                genres = [str(x) for x in (entry.get("entity_genres") or entity.get("genres") or []) if str(x).strip()]
            overview = str(entry.get("overview") or entity.get("overview") or "").strip()

            if _add_metadata(
                p, rating, iid, votes,
                overview=overview, genres=genres,
                year=str(entry.get("year") or entity.get("year") or year or ""),
                runtime_minutes=entry.get("runtime_minutes") or entity.get("runtime_minutes"),
                countries=entry.get("countries") or entity.get("countries") or [],
                original_title=str(entry.get("original_title") or entity.get("original_title") or ""),
                display_title=title,
            ):
                stats["programmes_enriched"] += 1
            if genres:
                stats["programmes_with_genres"] += 1
            if overview:
                stats["programmes_with_tmdb_overview"] += 1
            if entry.get("runtime_minutes") or entity.get("runtime_minutes"):
                stats["programmes_with_runtime"] += 1
            if entry.get("year") or entity.get("year") or year:
                stats["programmes_with_year"] += 1
            stats["metadata_matches"] += 1
            rows.append({
                "channel_id": cid, "title": title, "year": year, "type": typ, "status": "enriched",
                "source": entry.get("resolver", source), "imdb_id": iid, "imdb_rating": rating, "imdb_votes": votes,
                "detail": (
                    f"query={entry.get('query_title', canonical_title)}; lang={entry.get('language', language)}; "
                    f"attempt={entry.get('attempt', '')}; tmdb_title={entry.get('title', '')}; "
                    f"rating_source={entry.get('rating_source', '')}; votes={votes}; confidence={entry.get('confidence', '')}; "
                    f"genres={','.join(genres)}; overview={'yes' if overview else 'no'}"
                ),
            })
        elif entry:
            status = entry.get("status", "other")
            stats[f"result_{status}"] += 1
            rows.append({
                "channel_id": cid, "title": title, "year": year, "type": typ, "status": status,
                "source": entry.get("resolver", source), "imdb_id": entry.get("imdb_id", ""),
                "imdb_rating": entry.get("imdb_rating", ""), "imdb_votes": entry.get("imdb_votes", ""),
                "detail": f"query={entry.get('query_title', canonical_title)}; lang={entry.get('language', language)}; attempts={entry.get('attempts', '')}",
            })

    if previous_sigterm is not None:
        try:
            signal.signal(signal.SIGTERM, previous_sigterm)
        except (ValueError, OSError):
            pass

    if ratings_conn is not None:
        ratings_conn.close()
    if local_imdb_conn is not None:
        local_imdb_conn.close()

    db.conn.commit()
    db.checkpoint()
    db_counts = db.counts()
    db_path = str(db.path)
    db.close()

    unique = {}
    for row in rows:
        unique[(row["title"], row["year"], row["type"], row["status"])] = row
    report_rows = list(unique.values())

    print(
        f"[metadata] done; titles={title_budget.used}; http={http_budget.used}; matches={stats['metadata_matches']}; "
        f"sqlite_hits={stats['sqlite_title_hits']}; db_titles={db_counts['titles']}",
        flush=True,
    )

    return {
        "summary": {
            "mode": "fiction-only-ru-en+knowledge-first+rich-xmltv+official-local-imdb-v13-stage5",
            "metadata_version": METADATA_VERSION,
            "api_configured": bool(tmdb_key),
            "tmdb_configured": bool(tmdb_key),
            "omdb_removed": True,
            "imdb_scraping_removed": True,
            "imdb_ratings_source": "official-imdb-bulk-local-sqlite",
            "imdb_ratings_url": IMDB_RATINGS_URL,
            "imdb_dataset_refresh_hours": IMDB_DATASET_REFRESH_HOURS,
            "alias_file": ALIAS_FILE,
            "alias_entries": len(aliases),
            "sqlite_cache": True,
            "sqlite_db": db_path,
            "sqlite_title_entries": db_counts["titles"],
            "sqlite_imdb_entities": db_counts["imdb_entities"],
            "sqlite_learned_aliases": db_counts["aliases"],
            "legacy_json_cache_read_only_migration": True,
            "imdb_refresh_days": IMDB_REFRESH_DAYS,
            "max_unique_metadata_titles_per_run": max_titles,
            "unique_metadata_title_lookups_used": title_budget.used,
            "metadata_title_budget": max_titles,
            "metadata_http_budget": max_http_requests,
            "metadata_http_requests_used": http_budget.used,
            "metadata_http_requests_remaining": http_budget.remaining,
            "metadata_title_lookups_remaining": title_budget.remaining,
            "metadata_deadline_seconds": deadline_seconds,
            "metadata_stopped_reason": (
                stop_requested["reason"]
                or ("http_budget" if stats.get("http_budget_exhausted") else "")
                or ("title_budget" if title_budget.remaining == 0 else "")
                or "completed"
            ),
            "tmdb_new_title_resolutions": title_budget.used,
            **{k: int(v) for k, v in stats.items()},
            "unique_report_rows": len(report_rows),
        },
        "rows": report_rows,
    }
