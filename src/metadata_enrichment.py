from __future__ import annotations

import gzip
import json
import os
import re
import shutil
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

TMDB_URL = "https://api.themoviedb.org/3"
METADATA_VERSION = "9.0"
CACHE_SCHEMA = 9
CACHE_FILE = "metadata-cache.json"
IMDB_ENTITY_CACHE_FILE = "imdb-cache.json"
ALIAS_FILE = "metadata_aliases.json"
IMDB_ENTITY_CACHE_SCHEMA = 2
IMDB_REFRESH_DAYS = 30
IMDB_MISSING_RETRY_DAYS = 7
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
IMDB_RATINGS_GZ_FILE = "title.ratings.tsv.gz"
IMDB_RATINGS_DB_FILE = "imdb-ratings.sqlite3"
IMDB_DATASET_REFRESH_HOURS = 24

IMDB_RATING_RE = re.compile(r"(?i)\bIMDb\b\s*(?:rating|рейтинг)?\s*[:\[\(]?\s*([0-9](?:[\.,][0-9])?|10(?:[\.,]0)?)")
IMDB_ID_RE = re.compile(r"(?i)\b(tt\d{5,12})\b")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
MOVIE_WORDS = {"movie", "movies", "film", "films", "кино", "фильм", "фильмы", "cinema"}
SERIES_WORDS = {"series", "serial", "сериал", "сериалы", "tv series", "episode", "эпизод"}
MOVIE_GROUPS = {"Кино", "Кино 4K", "Кинозалы", "Кинозалы UA"}
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


def _add_metadata(programme: ET.Element, rating: str, imdb_id: str, imdb_votes: str = "") -> bool:
    changed = False
    rating = (rating or "").strip()
    imdb_id = (imdb_id or "").strip().lower()
    imdb_votes = (imdb_votes or "").strip()
    if rating and not any((r.get("system") or "").lower() == "imdb" for r in programme.findall("rating")):
        r = ET.Element("rating", {"system": "IMDb"})
        ET.SubElement(r, "value").text = f"{rating}/10"
        programme.append(r)
        changed = True
    if imdb_id and not any("imdb.com/title/" in (u.text or "").lower() for u in programme.findall("url")):
        u = ET.Element("url")
        u.text = f"https://www.imdb.com/title/{imdb_id}/"
        programme.append(u)
        changed = True
    if rating or imdb_id:
        desc = programme.find("desc")
        existing = (desc.text or "").strip() if desc is not None else ""
        if "imdb" not in existing.lower():
            bits = []
            if rating:
                bits.append(f"IMDb {rating}/10")
            if imdb_votes:
                bits.append(f"{imdb_votes} votes")
            if imdb_id:
                bits.append(imdb_id)
            if desc is None:
                desc = ET.Element("desc")
                programme.append(desc)
            suffix = " · ".join(bits)
            desc.text = f"{existing}  •  {suffix}" if existing else suffix
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
    base = (title or "").strip()
    variants: list[str] = []
    raw_variants = (
        base,
        base.replace("ё", "е").replace("Ё", "Е"),
        re.sub(r'[«»„“”"]', "", base),
        re.sub(r"\s*[-–—]\s*", " ", base),
    )
    for value in raw_variants:
        value = re.sub(r"\s+", " ", value).strip(' -–—:;,."')
        if value and value not in variants:
            variants.append(value)
    translit = _transliterate_ru(base)
    if translit and normalize_name(translit) != normalize_name(base) and translit not in variants:
        variants.append(translit)
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


def _http_json(url: str, timeout: int, headers=None, attempts: int = 3):
    req_headers = headers or {"User-Agent": "IPTV-EPG-Builder/9.0"}
    last_exc = None
    for attempt in range(max(1, attempts)):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(0.35 * (2 ** attempt))
    raise last_exc


def _tmdb_search(api_key: str, title: str, year: str, media_type: str, language: str = "en-US", timeout: int = 12):
    endpoint = "movie" if media_type == "movie" else "tv"
    p = {"api_key": api_key, "query": title, "include_adult": "false", "language": language}
    if year:
        p["primary_release_year" if media_type == "movie" else "first_air_date_year"] = year
    return _http_json(f"{TMDB_URL}/search/{endpoint}?" + urllib.parse.urlencode(p), timeout)


def _tmdb_external_ids(api_key: str, tmdb_id: int, media_type: str, timeout: int = 12):
    endpoint = "movie" if media_type == "movie" else "tv"
    return _http_json(f"{TMDB_URL}/{endpoint}/{tmdb_id}/external_ids?" + urllib.parse.urlencode({"api_key": api_key}), timeout)


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
    for q, y, lang, lookup_type, label in plans:
        if budget is not None and not budget.consume():
            return {"status": "budget_exhausted", "query_title": cleaned, "language": language, "attempts": len(attempts)}
        attempts.append((q, y, lang, lookup_type))
        payload = _tmdb_search(api_key, q, y, lookup_type, lang, timeout)
        cand = _best_tmdb_candidate(payload, q, y, lookup_type)
        if not cand:
            continue
        tmdb_id = cand.get("id")
        if not tmdb_id:
            continue
        if budget is not None and not budget.consume():
            return {"status": "budget_exhausted", "query_title": q, "language": lang, "attempts": len(attempts)}
        ext = _tmdb_external_ids(api_key, int(tmdb_id), lookup_type, timeout)
        imdb_id = str(ext.get("imdb_id") or "").strip().lower()
        result = {
            "tmdb_id": tmdb_id,
            "title": cand.get("title") or cand.get("name") or "",
            "original_title": cand.get("original_title") or cand.get("original_name") or "",
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
    tmdb_key = os.environ.get("TMDB_API_KEY", "").strip()
    max_requests = max(0, int(os.environ.get("METADATA_MAX_REQUESTS", "150") or 150))
    timeout = max(3, int(os.environ.get("METADATA_TIMEOUT", "12") or 12))
    budget = _Budget(max_requests)
    aliases = _load_metadata_aliases(root)

    cache_path = root / ".cache" / "metadata" / CACHE_FILE
    cache = _load_cache(cache_path)
    imdb_cache_path = root / ".cache" / "metadata" / IMDB_ENTITY_CACHE_FILE
    imdb_entities = _load_imdb_entity_cache(imdb_cache_path)
    imdb_cache_changed = False

    # v9 cache filenames are stable. Migrate the newest available legacy cache once.
    if not cache and not cache_path.exists():
        for legacy_name in ("metadata-v80.json", "metadata-v70.json", "metadata-v60.json", "metadata-v50.json"):
            legacy = root / ".cache" / "metadata" / legacy_name
            if legacy.exists():
                cache = _load_cache(legacy)
                if cache:
                    break
    if not imdb_entities and not imdb_cache_path.exists():
        for legacy_name in ("imdb-entities-v80.json", "imdb-entities-v70.json"):
            legacy = root / ".cache" / "metadata" / legacy_name
            if legacy.exists():
                imdb_entities = _load_imdb_entity_cache(legacy)
                if imdb_entities:
                    break

    groups: dict[str, str] = {}
    allowed: set[str] = set()
    for row in mappings:
        oid = (row.get("output_tvg_id") or "").strip()
        if oid:
            allowed.add(oid)
            groups.setdefault(oid, row.get("group", ""))

    stats = Counter()
    ratings_db_path = None
    ratings_conn = None

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

    def resolve_entity(iid: str):
        cached_entity = imdb_entities.get((iid or "").strip().lower())
        conn = ratings_conn
        if not (cached_entity and _imdb_entity_fresh(cached_entity)):
            conn = ensure_ratings_conn()
        return _resolve_imdb_entity(iid, imdb_entities, stats, conn)

    rows = []
    changed = False

    # In-run memo guarantees 120 episodes of one canonical series do not trigger 120 lookups.
    memo: dict[str, dict] = {}

    for p in tv.findall("programme"):
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
            if _add_metadata(p, rating, iid):
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
            cached = cache.get(key)
            if cached is not None and _negative_cache_fresh(cached):
                entry = cached
                source = "cache"
                stats["cache_hits"] += 1
            elif cached is not None:
                stats["stale_cache_retried"] += 1

            if entry is None:
                if not budget.allow():
                    stats["lookup_not_attempted"] += 1
                    continue
                try:
                    if not tmdb_key:
                        stats["lookup_not_attempted"] += 1
                        continue
                    entry = _tmdb_lookup_imdb(
                        tmdb_key, canonical_title, year, effective_type, language, timeout,
                        raw_title=title, budget=budget, aliases=aliases,
                    )
                    stats["tmdb_resolver_calls"] += 1
                    source = "tmdb"

                    if entry.get("status") == "found":
                        stats["tmdb_matches"] += 1
                        entity = resolve_entity(entry["imdb_id"])
                        imdb_cache_changed = True
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
                        previous_misses = int((cached or {}).get("miss_count") or 0)
                        entry["miss_count"] = previous_misses + 1

                    entry["cached_at"] = datetime.now(timezone.utc).isoformat()
                    if entry.get("status") != "budget_exhausted":
                        cache[key] = entry
                        changed = True
                    time.sleep(0.02)
                except Exception as exc:
                    stats["api_errors"] += 1
                    rows.append({
                        "channel_id": cid, "title": title, "year": year, "type": typ, "status": "api_error",
                        "source": "metadata-api", "imdb_id": "", "imdb_rating": "", "imdb_votes": "", "detail": str(exc)[:180],
                    })
                    continue

            # Successful title mappings reuse a separate IMDb-ID entity cache.
            # Rating/votes refresh at most every 30 days (7 days when both are missing).
            if entry and entry.get("status") == "found":
                try:
                    entity = resolve_entity(entry.get("imdb_id", ""))
                    if entity:
                        entry["imdb_rating"] = str(entity.get("rating") or "").strip()
                        entry["imdb_votes"] = _normalize_votes(entity.get("votes"))
                        entry["rating_source"] = str(entity.get("source") or "")
                        entry["rating_checked_at"] = str(entity.get("checked_at") or "")
                        entry["resolver"] = "tmdb+imdb-dataset" if entry.get("imdb_rating") or entry.get("imdb_votes") else "tmdb"
                        cache[key] = entry
                        changed = True
                        imdb_cache_changed = True
                except Exception:
                    stats["rating_refresh_errors"] += 1

            memo[key] = entry

        if entry and entry.get("status") == "found":
            rating = str(entry.get("imdb_rating", "")).strip()
            votes = _normalize_votes(entry.get("imdb_votes"))
            iid = str(entry.get("imdb_id", "")).strip()
            if _add_metadata(p, rating, iid, votes):
                stats["programmes_enriched"] += 1
            stats["metadata_matches"] += 1
            rows.append({
                "channel_id": cid, "title": title, "year": year, "type": typ, "status": "enriched",
                "source": entry.get("resolver", source), "imdb_id": iid, "imdb_rating": rating, "imdb_votes": votes,
                "detail": (
                    f"query={entry.get('query_title', canonical_title)}; lang={entry.get('language', language)}; "
                    f"attempt={entry.get('attempt', '')}; tmdb_title={entry.get('title', '')}; "
                    f"rating_source={entry.get('rating_source', '')}; votes={votes}; confidence={entry.get('confidence', '')}"
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

    if ratings_conn is not None:
        ratings_conn.close()

    if changed:
        _save_cache(cache_path, cache)
    if imdb_cache_changed:
        _save_imdb_entity_cache(imdb_cache_path, imdb_entities)

    if changed or imdb_cache_changed:
        # v9 owns stable metadata-cache.json + imdb-cache.json.
        # XMLTV fallback caches under .cache/epg are intentionally untouched.
        for obsolete in (
            "metadata-v80.json", "imdb-entities-v80.json", "metadata-v70.json", "imdb-entities-v70.json", "metadata-v60.json", "metadata-v50.json", "metadata-v42.json",
            "metadata-v41.json", "metadata.json", "omdb.json"
        ):
            try:
                (root / ".cache" / "metadata" / obsolete).unlink()
            except FileNotFoundError:
                pass

    unique = {}
    for row in rows:
        unique[(row["title"], row["year"], row["type"], row["status"])] = row
    report_rows = list(unique.values())

    return {
        "summary": {
            "mode": "fiction-only-ru-en+tmdb-cascade+aliases+confidence+official-imdb-ratings-dataset-v9.0",
            "metadata_version": METADATA_VERSION,
            "api_configured": bool(tmdb_key),
            "tmdb_configured": bool(tmdb_key),
            "omdb_removed": True,
            "imdb_scraping_removed": True,
            "imdb_ratings_source": "official-contributor-dataset",
            "imdb_ratings_url": IMDB_RATINGS_URL,
            "imdb_dataset_refresh_hours": IMDB_DATASET_REFRESH_HOURS,
            "alias_file": ALIAS_FILE,
            "alias_entries": len(aliases),
            "imdb_direct_enabled": False,
            "imdb_entity_cache_file": IMDB_ENTITY_CACHE_FILE,
            "imdb_entity_cache_entries": len(imdb_entities),
            "imdb_refresh_days": IMDB_REFRESH_DAYS,
            "max_tmdb_requests_per_run": max_requests,
            "tmdb_requests_used": budget.used,
            "cache_file": CACHE_FILE,
            "cache_entries": len(cache),
            **{k: int(v) for k, v in stats.items()},
            "unique_report_rows": len(report_rows),
        },
        "rows": report_rows,
    }
