from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from .utils import normalize_name

OMDB_URL = "https://www.omdbapi.com/"
IMDB_RATING_RE = re.compile(r"(?i)\bIMDb\b\s*(?:rating|рейтинг)?\s*[:\[\(]?\s*([0-9](?:[\.,][0-9])?|10(?:[\.,]0)?)")
IMDB_ID_RE = re.compile(r"(?i)\b(tt\d{5,12})\b")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
MOVIE_WORDS = {"movie", "movies", "film", "films", "кино", "фильм", "фильмы", "cinema"}
SERIES_WORDS = {"series", "serial", "сериал", "сериалы", "tv series", "episode", "эпизод"}
MOVIE_GROUPS = {"Кино", "Кино 4K", "Кинозалы", "Кинозалы UA"}


def _text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _year(programme: ET.Element) -> str:
    date = _text(programme, "date")
    m = YEAR_RE.search(date)
    if m:
        return m.group(1)
    for value in (_text(programme, "title"), _text(programme, "desc")):
        m = YEAR_RE.search(value)
        if m:
            return m.group(1)
    return ""


def _categories(programme: ET.Element) -> set[str]:
    out = set()
    for elem in programme.findall("category"):
        value = normalize_name(elem.text or "")
        if value:
            out.add(value)
    return out


def _media_type(programme: ET.Element, group: str) -> str:
    categories = _categories(programme)
    joined = " ".join(categories)
    if programme.find("episode-num") is not None or any(word in joined for word in SERIES_WORDS):
        return "series"
    if any(word in joined for word in MOVIE_WORDS):
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
                value_elem = elem.find("value")
                value = (value_elem.text or "").strip() if value_elem is not None else ""
                m = re.search(r"([0-9](?:[\.,][0-9])?|10(?:[\.,]0)?)", value)
                if m:
                    rating = m.group(1).replace(",", ".")
                    break
    return rating, imdb_id


def _add_metadata(programme: ET.Element, rating: str, imdb_id: str) -> bool:
    changed = False
    rating = (rating or "").strip()
    imdb_id = (imdb_id or "").strip().lower()

    has_rating = any((r.get("system") or "").strip().lower() == "imdb" for r in programme.findall("rating"))
    if rating and not has_rating:
        r = ET.Element("rating", {"system": "IMDb"})
        v = ET.SubElement(r, "value")
        v.text = f"{rating}/10"
        programme.append(r)
        changed = True

    if imdb_id:
        imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
        has_url = any("imdb.com/title/" in (u.text or "").lower() for u in programme.findall("url"))
        if not has_url:
            u = ET.Element("url")
            u.text = imdb_url
            programme.append(u)
            changed = True

    if rating or imdb_id:
        desc = programme.find("desc")
        existing = (desc.text or "").strip() if desc is not None else ""
        if "imdb" not in existing.lower():
            bits = []
            if rating:
                bits.append(f"IMDb {rating}/10")
            if imdb_id:
                bits.append(imdb_id)
            suffix = " · ".join(bits)
            if desc is None:
                desc = ET.Element("desc")
                programme.append(desc)
            desc.text = f"{existing}  •  {suffix}" if existing else suffix
            changed = True
    return changed


def _load_cache(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _cache_key(title: str, year: str, media_type: str) -> str:
    return "|".join((normalize_name(title), year or "", media_type or ""))


def _title_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _omdb_lookup(api_key: str, title: str, year: str, media_type: str, timeout: int = 12) -> dict:
    params = {"apikey": api_key, "t": title, "plot": "short", "r": "json"}
    if year:
        params["y"] = year
    if media_type in {"movie", "series"}:
        params["type"] = media_type
    url = OMDB_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "IPTV-EPG-Builder/4.1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def enrich_metadata(tv: ET.Element, mappings: list[dict], root: Path, output: Path) -> dict:
    api_key = os.environ.get("OMDB_API_KEY", "").strip()
    max_requests = max(0, int(os.environ.get("OMDB_MAX_REQUESTS", "150") or 150))
    timeout = max(3, int(os.environ.get("OMDB_TIMEOUT", "12") or 12))
    cache_path = root / ".cache" / "metadata" / "omdb.json"
    cache = _load_cache(cache_path)

    groups_by_id = {}
    allowed_ids = set()
    for row in mappings:
        out_id = (row.get("output_tvg_id") or "").strip()
        if out_id:
            allowed_ids.add(out_id)
            groups_by_id.setdefault(out_id, row.get("group", ""))

    stats = Counter()
    rows = []
    requests = 0
    changed_cache = False

    for programme in tv.findall("programme"):
        channel_id = (programme.get("channel") or "").strip()
        if channel_id not in allowed_ids:
            continue
        stats["programmes_considered"] += 1
        title = _text(programme, "title")
        if not title:
            continue

        rating, imdb_id = _existing_imdb(programme)
        if rating or imdb_id:
            stats["programmes_with_existing_imdb"] += 1
            if _add_metadata(programme, rating, imdb_id):
                stats["existing_metadata_normalized"] += 1
            continue

        media_type = _media_type(programme, groups_by_id.get(channel_id, ""))
        if not media_type:
            stats["not_movie_or_series"] += 1
            continue
        if len(normalize_name(title)) < 3:
            stats["title_too_short"] += 1
            continue

        year = _year(programme)
        key = _cache_key(title, year, media_type)
        entry = cache.get(key)
        source = "cache"
        if entry is not None:
            stats["cache_hits"] += 1
        elif not api_key or requests >= max_requests:
            stats["lookup_not_attempted"] += 1
            continue
        else:
            source = "omdb"
            try:
                payload = _omdb_lookup(api_key, title, year, media_type, timeout=timeout)
                requests += 1
                stats["api_requests"] += 1
                if str(payload.get("Response", "")).lower() != "true":
                    entry = {"status": "not_found", "title": title, "year": year, "type": media_type}
                else:
                    returned_title = str(payload.get("Title", "")).strip()
                    returned_year = str(payload.get("Year", "")).strip()
                    returned_type = str(payload.get("Type", "")).strip().lower()
                    sim = _title_similarity(title, returned_title)
                    year_ok = True
                    if year:
                        m = YEAR_RE.search(returned_year)
                        year_ok = bool(m and abs(int(m.group(1)) - int(year)) <= 1)
                    type_ok = not returned_type or returned_type == media_type
                    imdb_rating = str(payload.get("imdbRating", "")).strip()
                    if imdb_rating.upper() == "N/A":
                        imdb_rating = ""
                    found_id = str(payload.get("imdbID", "")).strip().lower()
                    if sim >= 0.90 and year_ok and type_ok and IMDB_ID_RE.fullmatch(found_id or ""):
                        entry = {
                            "status": "found", "title": returned_title, "year": returned_year,
                            "type": returned_type or media_type, "imdb_id": found_id,
                            "imdb_rating": imdb_rating, "similarity": round(sim, 3),
                        }
                    else:
                        entry = {
                            "status": "rejected", "title": returned_title, "year": returned_year,
                            "type": returned_type, "imdb_id": found_id,
                            "similarity": round(sim, 3), "year_ok": year_ok, "type_ok": type_ok,
                        }
                cache[key] = entry
                changed_cache = True
                time.sleep(0.03)
            except Exception as exc:
                stats["api_errors"] += 1
                rows.append({
                    "channel_id": channel_id, "title": title, "year": year, "type": media_type,
                    "status": "api_error", "source": "omdb", "imdb_id": "", "imdb_rating": "",
                    "detail": str(exc)[:180],
                })
                continue

        if entry and entry.get("status") == "found":
            found_rating = str(entry.get("imdb_rating", "")).strip()
            found_id = str(entry.get("imdb_id", "")).strip()
            if _add_metadata(programme, found_rating, found_id):
                stats["programmes_enriched"] += 1
            stats["metadata_matches"] += 1
            rows.append({
                "channel_id": channel_id, "title": title, "year": year, "type": media_type,
                "status": "enriched", "source": source, "imdb_id": found_id,
                "imdb_rating": found_rating, "detail": entry.get("title", ""),
            })
        elif entry:
            stats[f"cache_{entry.get('status','other')}"] += 1

    if changed_cache:
        _save_cache(cache_path, cache)

    unique = {}
    for row in rows:
        k = (row["title"], row["year"], row["type"], row["status"])
        unique[k] = row
    report_rows = list(unique.values())

    summary = {
        "mode": "existing-imdb-normalization+optional-omdb",
        "api_configured": bool(api_key),
        "max_api_requests_per_run": max_requests,
        "cache_entries": len(cache),
        **{k: int(v) for k, v in stats.items()},
        "unique_report_rows": len(report_rows),
    }
    return {"summary": summary, "rows": report_rows}
