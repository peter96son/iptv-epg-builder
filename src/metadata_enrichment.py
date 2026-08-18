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
TMDB_URL = "https://api.themoviedb.org/3"
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


def _http_json(url: str, timeout: int, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "IPTV-EPG-Builder/4.2"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _omdb_lookup_title(api_key: str, title: str, year: str, media_type: str, timeout: int = 12) -> dict:
    params = {"apikey": api_key, "t": title, "plot": "short", "r": "json"}
    if year:
        params["y"] = year
    if media_type in {"movie", "series"}:
        params["type"] = media_type
    return _http_json(OMDB_URL + "?" + urllib.parse.urlencode(params), timeout)


def _omdb_lookup_id(api_key: str, imdb_id: str, timeout: int = 12) -> dict:
    return _http_json(OMDB_URL + "?" + urllib.parse.urlencode({"apikey": api_key, "i": imdb_id, "plot": "short", "r": "json"}), timeout)


def _tmdb_search(api_key: str, title: str, year: str, media_type: str, timeout: int = 12) -> dict:
    endpoint = "movie" if media_type == "movie" else "tv"
    params = {"api_key": api_key, "query": title, "include_adult": "false"}
    if year:
        params["year" if media_type == "movie" else "first_air_date_year"] = year
    return _http_json(f"{TMDB_URL}/search/{endpoint}?" + urllib.parse.urlencode(params), timeout)


def _tmdb_external_ids(api_key: str, tmdb_id: int, media_type: str, timeout: int = 12) -> dict:
    endpoint = "movie" if media_type == "movie" else "tv"
    return _http_json(f"{TMDB_URL}/{endpoint}/{tmdb_id}/external_ids?" + urllib.parse.urlencode({"api_key": api_key}), timeout)


def _best_tmdb_candidate(payload: dict, title: str, year: str, media_type: str) -> dict | None:
    best = None
    best_score = 0.0
    for item in (payload.get("results") or [])[:10]:
        names = [str(item.get("title") or item.get("name") or "").strip(), str(item.get("original_title") or item.get("original_name") or "").strip()]
        sim = max((_title_similarity(title, n) for n in names if n), default=0.0)
        date = str(item.get("release_date") or item.get("first_air_date") or "")
        m = YEAR_RE.search(date)
        cyear = m.group(1) if m else ""
        year_ok = True
        if year and cyear:
            year_ok = abs(int(year)-int(cyear)) <= 1
        elif year and not cyear:
            year_ok = False
        score = sim + (0.08 if year and year_ok else 0.0)
        if year_ok and sim >= 0.84 and score > best_score:
            best = dict(item)
            best["_similarity"] = round(sim,3)
            best["_candidate_year"] = cyear
            best_score = score
    return best


def _tmdb_lookup_imdb(api_key: str, title: str, year: str, media_type: str, timeout: int = 12) -> dict:
    candidate = _best_tmdb_candidate(_tmdb_search(api_key, title, year, media_type, timeout), title, year, media_type)
    if not candidate:
        return {"status":"not_found"}
    tmdb_id = candidate.get("id")
    if not tmdb_id:
        return {"status":"not_found"}
    ext = _tmdb_external_ids(api_key, int(tmdb_id), media_type, timeout)
    imdb_id = str(ext.get("imdb_id") or "").strip().lower()
    if not IMDB_ID_RE.fullmatch(imdb_id or ""):
        return {"status":"no_imdb_id","tmdb_id":tmdb_id,"title":candidate.get("title") or candidate.get("name") or "","similarity":candidate.get("_similarity",0)}
    return {"status":"found","tmdb_id":tmdb_id,"title":candidate.get("title") or candidate.get("name") or "","original_title":candidate.get("original_title") or candidate.get("original_name") or "","year":candidate.get("_candidate_year",year),"similarity":candidate.get("_similarity",0),"imdb_id":imdb_id}


def _validate_omdb_payload(payload: dict, title: str, year: str, media_type: str) -> dict:
    if str(payload.get("Response","")).lower() != "true":
        return {"status":"not_found","title":title,"year":year,"type":media_type}
    returned_title=str(payload.get("Title","")).strip(); returned_year=str(payload.get("Year","")).strip(); returned_type=str(payload.get("Type","")).strip().lower()
    sim=_title_similarity(title,returned_title); year_ok=True
    if year:
        m=YEAR_RE.search(returned_year); year_ok=bool(m and abs(int(m.group(1))-int(year))<=1)
    type_ok=not returned_type or returned_type==media_type
    rating=str(payload.get("imdbRating","")).strip(); rating="" if rating.upper()=="N/A" else rating
    imdb_id=str(payload.get("imdbID","")).strip().lower()
    if sim>=0.90 and year_ok and type_ok and IMDB_ID_RE.fullmatch(imdb_id or ""):
        return {"status":"found","title":returned_title,"year":returned_year,"type":returned_type or media_type,"imdb_id":imdb_id,"imdb_rating":rating,"similarity":round(sim,3)}
    return {"status":"rejected","title":returned_title,"year":returned_year,"type":returned_type,"imdb_id":imdb_id,"similarity":round(sim,3),"year_ok":year_ok,"type_ok":type_ok}


def enrich_metadata(tv: ET.Element, mappings: list[dict], root: Path, output: Path) -> dict:
    omdb_key=os.environ.get("OMDB_API_KEY","").strip(); tmdb_key=os.environ.get("TMDB_API_KEY","").strip()
    max_requests=max(0,int(os.environ.get("METADATA_MAX_REQUESTS",os.environ.get("OMDB_MAX_REQUESTS","150")) or 150)); timeout=max(3,int(os.environ.get("METADATA_TIMEOUT",os.environ.get("OMDB_TIMEOUT","12")) or 12))
    cache_path=root/".cache"/"metadata"/"metadata.json"; cache=_load_cache(cache_path)
    groups_by_id={}; allowed_ids=set()
    for row in mappings:
        out_id=(row.get("output_tvg_id") or "").strip()
        if out_id: allowed_ids.add(out_id); groups_by_id.setdefault(out_id,row.get("group",""))
    stats=Counter(); rows=[]; requests=0; changed_cache=False
    for programme in tv.findall("programme"):
        channel_id=(programme.get("channel") or "").strip()
        if channel_id not in allowed_ids: continue
        stats["programmes_considered"]+=1; title=_text(programme,"title")
        if not title: continue
        rating,imdb_id=_existing_imdb(programme)
        if rating or imdb_id:
            stats["programmes_with_existing_imdb"]+=1
            if _add_metadata(programme,rating,imdb_id): stats["existing_metadata_normalized"]+=1
            continue
        media_type=_media_type(programme,groups_by_id.get(channel_id,""))
        if not media_type: stats["not_movie_or_series"]+=1; continue
        if len(normalize_name(title))<3: stats["title_too_short"]+=1; continue
        year=_year(programme); key=_cache_key(title,year,media_type); entry=cache.get(key); source="cache"
        if entry is not None:
            stats["cache_hits"]+=1
        elif requests>=max_requests:
            stats["lookup_not_attempted"]+=1; continue
        else:
            try:
                if tmdb_key:
                    tmdb=_tmdb_lookup_imdb(tmdb_key,title,year,media_type,timeout); requests+=1; stats["tmdb_requests"]+=1
                    if tmdb.get("status")=="found":
                        imdb_id=tmdb["imdb_id"]; imdb_rating=""
                        if omdb_key and requests<max_requests:
                            payload=_omdb_lookup_id(omdb_key,imdb_id,timeout); requests+=1; stats["omdb_id_requests"]+=1
                            if str(payload.get("Response","")).lower()=="true":
                                imdb_rating=str(payload.get("imdbRating","")).strip(); imdb_rating="" if imdb_rating.upper()=="N/A" else imdb_rating
                        entry={"status":"found","title":tmdb.get("title",""),"original_title":tmdb.get("original_title",""),"year":tmdb.get("year",year),"type":media_type,"imdb_id":imdb_id,"imdb_rating":imdb_rating,"similarity":tmdb.get("similarity",0),"resolver":"tmdb+omdb" if omdb_key else "tmdb"}
                        source=entry["resolver"]; stats["tmdb_matches"]+=1
                    else:
                        entry={"status":tmdb.get("status","not_found"),"title":title,"year":year,"type":media_type,"resolver":"tmdb"}; stats[f"tmdb_{entry['status']}"]+=1
                elif omdb_key:
                    entry=_validate_omdb_payload(_omdb_lookup_title(omdb_key,title,year,media_type,timeout),title,year,media_type); requests+=1; stats["omdb_title_requests"]+=1; entry["resolver"]="omdb-title"; source="omdb-title"
                else:
                    stats["lookup_not_attempted"]+=1; continue
                cache[key]=entry; changed_cache=True; time.sleep(0.03)
            except Exception as exc:
                stats["api_errors"]+=1; rows.append({"channel_id":channel_id,"title":title,"year":year,"type":media_type,"status":"api_error","source":"metadata-api","imdb_id":"","imdb_rating":"","detail":str(exc)[:180]}); continue
        if entry and entry.get("status")=="found":
            found_rating=str(entry.get("imdb_rating","")).strip(); found_id=str(entry.get("imdb_id","")).strip()
            if _add_metadata(programme,found_rating,found_id): stats["programmes_enriched"]+=1
            stats["metadata_matches"]+=1; rows.append({"channel_id":channel_id,"title":title,"year":year,"type":media_type,"status":"enriched","source":source if source!="cache" else entry.get("resolver","cache"),"imdb_id":found_id,"imdb_rating":found_rating,"detail":entry.get("title","")})
        elif entry: stats[f"cache_{entry.get('status','other')}"]+=1
    if changed_cache: _save_cache(cache_path,cache)
    unique={}
    for row in rows: unique[(row["title"],row["year"],row["type"],row["status"])]=row
    report_rows=list(unique.values())
    summary={"mode":"existing-imdb+tmdb-resolver+omdb-rating","api_configured":bool(omdb_key or tmdb_key),"tmdb_configured":bool(tmdb_key),"omdb_configured":bool(omdb_key),"max_api_requests_per_run":max_requests,"cache_entries":len(cache),**{k:int(v) for k,v in stats.items()},"unique_report_rows":len(report_rows)}
    return {"summary":summary,"rows":report_rows}
