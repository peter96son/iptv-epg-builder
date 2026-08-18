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

LANG_MAP = {
    "ru":"ru-RU","uk":"uk-UA","ua":"uk-UA","be":"be-BY","de":"de-DE","pl":"pl-PL",
    "it":"it-IT","fr":"fr-FR","es":"es-ES","pt":"pt-PT","tr":"tr-TR",
    "ro":"ro-RO","bg":"bg-BG","el":"el-GR","he":"he-IL","cs":"cs-CZ",
    "sk":"sk-SK","hu":"hu-HU","lt":"lt-LT","lv":"lv-LV","et":"et-EE",
    "hr":"hr-HR","en":"en-US",
}

def _text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""

def _year(programme: ET.Element) -> str:
    date = _text(programme, "date")
    m = YEAR_RE.search(date)
    if m:
        return m.group(1)
    # Description-derived years are intentionally NOT used as a hard TMDb filter.
    # They may describe a season/event rather than the production year.
    title = _text(programme, "title")
    m = YEAR_RE.search(title)
    return m.group(1) if m else ""

def _categories(programme: ET.Element) -> set[str]:
    out=set()
    for elem in programme.findall("category"):
        v=normalize_name(elem.text or "")
        if v: out.add(v)
    return out

DOCUMENTARY_WORDS = {
    "documentary", "documentaries", "doc", "docs",
    "документальный", "документальные", "док", "документалистика",
    "познавательный", "познавательные", "factual"
}

def _is_fiction_candidate(programme: ET.Element, group: str) -> bool:
    title = _text(programme, "title").strip().lower()
    cats = _categories(programme)
    joined = " ".join(cats)

    # Explicit documentary/programme prefixes: never spend TMDb/OMDb quota.
    if re.match(r"^\s*(?:д/с|д/ф)\b", title):
        return False

    # Documentary/factual categories.
    if any(word in joined for word in DOCUMENTARY_WORDS):
        return False

    # Explicit fiction prefixes are allowed.
    if re.match(r"^\s*(?:х/ф|т/с|сериал|фильм|кино)\b", title):
        return True

    # Movie groups are fiction-biased; series/movie category can also allow.
    if group in MOVIE_GROUPS:
        return True
    if any(word in joined for word in MOVIE_WORDS | SERIES_WORDS):
        return True

    return False

def _media_type(programme: ET.Element, group: str) -> str:
    joined=" ".join(_categories(programme)); title=_text(programme,"title").strip().lower()
    if re.match(r"^\s*(?:д/с|д/ф)\b",title): return ""
    if re.match(r"^\s*(?:т/с|сериал)\b",title): return "series"
    if re.match(r"^\s*(?:х/ф|фильм|кино)\b",title): return "movie"
    if programme.find("episode-num") is not None or any(w in joined for w in SERIES_WORDS): return "series"
    if any(w in joined for w in MOVIE_WORDS): return "movie"
    if group in MOVIE_GROUPS: return "movie"
    return ""

def _existing_imdb(programme: ET.Element):
    desc=_text(programme,"desc"); rating=""; imdb_id=""
    m=IMDB_RATING_RE.search(desc)
    if m: rating=m.group(1).replace(",",".")
    m=IMDB_ID_RE.search(desc)
    if m: imdb_id=m.group(1).lower()
    if not imdb_id:
        for elem in programme.findall("url"):
            m=IMDB_ID_RE.search(elem.text or "")
            if m: imdb_id=m.group(1).lower(); break
    if not rating:
        for elem in programme.findall("rating"):
            if (elem.get("system") or "").strip().lower()=="imdb":
                val=elem.find("value"); text=(val.text or "").strip() if val is not None else ""
                m=re.search(r"([0-9](?:[\.,][0-9])?|10(?:[\.,]0)?)",text)
                if m: rating=m.group(1).replace(",","."); break
    return rating, imdb_id

def _add_metadata(programme: ET.Element, rating: str, imdb_id: str) -> bool:
    changed=False; rating=(rating or "").strip(); imdb_id=(imdb_id or "").strip().lower()
    if rating and not any((r.get("system") or "").lower()=="imdb" for r in programme.findall("rating")):
        r=ET.Element("rating",{"system":"IMDb"}); ET.SubElement(r,"value").text=f"{rating}/10"; programme.append(r); changed=True
    if imdb_id and not any("imdb.com/title/" in (u.text or "").lower() for u in programme.findall("url")):
        u=ET.Element("url"); u.text=f"https://www.imdb.com/title/{imdb_id}/"; programme.append(u); changed=True
    if rating or imdb_id:
        desc=programme.find("desc"); existing=(desc.text or "").strip() if desc is not None else ""
        if "imdb" not in existing.lower():
            bits=[]
            if rating: bits.append(f"IMDb {rating}/10")
            if imdb_id: bits.append(imdb_id)
            if desc is None: desc=ET.Element("desc"); programme.append(desc)
            suffix=" · ".join(bits); desc.text=f"{existing}  •  {suffix}" if existing else suffix; changed=True
    return changed

def _detect_language(title: str) -> str:
    t = title or ""
    low = t.lower()
    if any(ch in low for ch in "іїєґ"):
        return "uk-UA"
    if "ў" in low:
        return "be-BY"
    cyr = sum(1 for c in t if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in t if c.isascii() and c.isalpha())
    return "ru-RU" if cyr > lat and cyr else "en-US"

def _programme_language(programme: ET.Element, title: str) -> str:
    e=programme.find("title"); lang=(e.get("lang") or "").strip().lower() if e is not None else ""
    if lang:
        return LANG_MAP.get(lang.split("-")[0], lang)
    return _detect_language(title)

def _clean_search_title(title: str) -> str:
    raw=(title or "").strip()
    is_series=bool(re.match(r"(?i)^\s*(?:т/с|д/с|сериал)\b",raw))
    x=re.sub(r"(?i)^\s*(?:х/ф|м/ф|т/с|д/с|д/ф|сериал|фильм|кино)\s*[:.\-–—]?\s*","",raw)
    x=re.sub(r"\s*[\[(]\s*\d{1,2}\+\s*[\])]\s*"," ",x)
    x=re.sub(r"\s*[\[(]?\s*(?:19\d{2}|20\d{2})\s*[\])]?\s*[.]?\s*$","",x)
    x=re.sub(r"(?i)[,.;:]?\s*\d+\s*(?:и|і|&|and|-)\s*\d+\s*[сc]\.?\s*$","",x)
    x=re.sub(r"(?i)[,.;:]?\s*\d+\s*[сc]\.?\s*$","",x)
    x=re.sub(r"(?i)\s+(?:серия|сер\.|эпизод|episode)\s*\d+\b.*$","",x)
    if is_series:
        x=re.sub(r"\s+\d+\.?\s*$","",x)
    return re.sub(r"\s+"," ",x).strip(" -–—:;,.") or raw

def _canonical_metadata_title(title: str, media_type: str) -> str:
    base = _clean_search_title(title)
    if media_type == "series":
        base = re.sub(r"\s*\([^()]{1,180}\)\s*$", "", base).strip()
        base = re.sub(r"\s+", " ", base).strip(" -–—:;,.")
    return base or _clean_search_title(title)

def _effective_metadata_type(raw_title: str, media_type: str) -> str:
    raw = raw_title or ""
    if media_type == "movie":
        if re.search(r"(?i)\b\d+\s*[сc]\.?\s*$", raw):
            return "series"
        if re.search(r"(?i)\b\d+\s*(?:и|і|&|and|-)\s*\d+\s*[сc]\.?\s*$", raw):
            return "series"
    return media_type

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
        "в приближении",
        "крупным планом",
        "показ класичних фільмів",
        "показ драматичних фільмів",
        "світові шедеври кіномистецтва",
    )):
        return True
    if re.match(r"(?i)^\s*spotlight\s*[,.:;-]?\s*\d+\s*[сc]\.?\s*$", raw):
        return True
    return False


def _load_cache(path: Path) -> dict:
    try:
        v=json.loads(path.read_text(encoding="utf-8")); return v if isinstance(v,dict) else {}
    except (OSError,json.JSONDecodeError): return {}

def _save_cache(path: Path, cache: dict):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(cache,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(tmp,path)

def _cache_key(title,year,media_type,language): return "|".join((normalize_name(title),year or "",media_type or "",language or ""))

def _title_similarity(a,b):
    na,nb=normalize_name(a),normalize_name(b)
    if not na or not nb: return 0.0
    if na==nb: return 1.0
    return SequenceMatcher(None,na,nb).ratio()

def _http_json(url,timeout,headers=None):
    req=urllib.request.Request(url,headers=headers or {"User-Agent":"IPTV-EPG-Builder/5.0"})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode("utf-8","replace"))

def _omdb_lookup_id(api_key,imdb_id,timeout=12):
    return _http_json(OMDB_URL+"?"+urllib.parse.urlencode({"apikey":api_key,"i":imdb_id,"plot":"short","r":"json"}),timeout)

def _omdb_lookup_title(api_key,title,year,media_type,timeout=12):
    p={"apikey":api_key,"t":title,"plot":"short","r":"json"}
    if year:p["y"]=year
    if media_type in {"movie","series"}:p["type"]=media_type
    return _http_json(OMDB_URL+"?"+urllib.parse.urlencode(p),timeout)

def _tmdb_search(api_key,title,year,media_type,language="en-US",timeout=12):
    endpoint="movie" if media_type=="movie" else "tv"
    p={"api_key":api_key,"query":title,"include_adult":"false","language":language}
    if year:
        p["primary_release_year" if media_type=="movie" else "first_air_date_year"]=year
    return _http_json(f"{TMDB_URL}/search/{endpoint}?"+urllib.parse.urlencode(p),timeout)

def _tmdb_external_ids(api_key,tmdb_id,media_type,timeout=12):
    endpoint="movie" if media_type=="movie" else "tv"
    return _http_json(f"{TMDB_URL}/{endpoint}/{tmdb_id}/external_ids?"+urllib.parse.urlencode({"api_key":api_key}),timeout)

def _best_tmdb_candidate(payload,title,year,media_type):
    best=None; best_score=0.0
    for item in (payload.get("results") or [])[:10]:
        names=[str(item.get("title") or item.get("name") or "").strip(),str(item.get("original_title") or item.get("original_name") or "").strip()]
        sim=max((_title_similarity(title,n) for n in names if n),default=0.0)
        date=str(item.get("release_date") or item.get("first_air_date") or ""); m=YEAR_RE.search(date); cy=m.group(1) if m else ""
        year_ok=True
        if year and cy: year_ok=abs(int(year)-int(cy))<=1
        # If TMDb has no date, don't kill an otherwise exact localized title.
        score=sim+(0.08 if year and cy and year_ok else 0.0)
        if year_ok and sim>=0.80 and score>best_score:
            best=dict(item); best["_similarity"]=round(sim,3); best["_candidate_year"]=cy; best_score=score
    return best

def _tmdb_lookup_imdb(api_key: str, title: str, year: str, media_type: str, language: str = "en-US", timeout: int = 12, raw_title: str = "") -> dict:
    cleaned = _canonical_metadata_title(title, media_type)
    attempts = []
    plans = [
        (cleaned, year, language, media_type, "localized+year"),
        (cleaned, "", language, media_type, "localized-no-year"),
    ]
    if media_type == "series":
        root = _series_root_fallback(cleaned)
        if root and root != cleaned:
            plans += [
                (root, year, language, "series", "series-root+year"),
                (root, "", language, "series", "series-root-no-year"),
            ]
    other_type = "series" if media_type == "movie" else "movie"
    type_hint_title = raw_title or title or ""
    multipart_hint = bool(
        re.search(r"(?i)\b\d+\s*[сc]\.?\s*$", type_hint_title)
        or re.search(r"(?i)\b\d+\s*(?:и|і|&|and|-)\s*\d+\s*[сc]\.?\s*$", type_hint_title)
        or re.search(r"(?i)^\s*(?:т/с|д/с)\b", type_hint_title)
    )
    if multipart_hint:
        plans += [
            (cleaned, year, language, other_type, "cross-type+year"),
            (cleaned, "", language, other_type, "cross-type-no-year"),
        ]
    if language != "en-US":
        plans += [
            (cleaned, year, "en-US", media_type, "english+year"),
            (cleaned, "", "en-US", media_type, "english-no-year"),
        ]
    for q, y, lang, lookup_type, label in plans:
        key = (q, y, lang, lookup_type)
        if key in attempts or not q:
            continue
        attempts.append(key)
        payload = _tmdb_search(api_key, q, y, lookup_type, lang, timeout)
        cand = _best_tmdb_candidate(payload, q, y, lookup_type)
        if not cand:
            continue
        tmdb_id = cand.get("id")
        if not tmdb_id:
            continue
        ext = _tmdb_external_ids(api_key, int(tmdb_id), lookup_type, timeout)
        imdb_id = str(ext.get("imdb_id") or "").strip().lower()
        if IMDB_ID_RE.fullmatch(imdb_id or ""):
            return {"status":"found","tmdb_id":tmdb_id,"title":cand.get("title") or cand.get("name") or "",
                    "original_title":cand.get("original_title") or cand.get("original_name") or "",
                    "year":cand.get("_candidate_year",year),"similarity":cand.get("_similarity",0),
                    "imdb_id":imdb_id,"attempt":label,"language":lang,"query_title":q,
                    "attempts":len(attempts),"resolved_media_type":lookup_type}
        return {"status":"no_imdb_id","tmdb_id":tmdb_id,"title":cand.get("title") or cand.get("name") or "",
                "similarity":cand.get("_similarity",0),"attempt":label,"language":lang,
                "query_title":q,"attempts":len(attempts),"resolved_media_type":lookup_type}
    return {"status":"not_found","query_title":cleaned,"language":language,"attempts":len(attempts)}

def _validate_omdb_payload(payload,title,year,media_type):
    if str(payload.get("Response","")).lower()!="true": return {"status":"not_found"}
    rt=str(payload.get("Title","")).strip(); ry=str(payload.get("Year","")).strip(); typ=str(payload.get("Type","")).strip().lower(); sim=_title_similarity(title,rt)
    year_ok=True
    if year:
        m=YEAR_RE.search(ry); year_ok=bool(m and abs(int(m.group(1))-int(year))<=1)
    iid=str(payload.get("imdbID","")).strip().lower(); rating=str(payload.get("imdbRating","")).strip(); rating="" if rating.upper()=="N/A" else rating
    if sim>=0.90 and year_ok and (not typ or typ==media_type) and IMDB_ID_RE.fullmatch(iid or ""):
        return {"status":"found","title":rt,"year":ry,"type":typ or media_type,"imdb_id":iid,"imdb_rating":rating,"similarity":round(sim,3)}
    return {"status":"rejected","title":rt,"year":ry,"type":typ,"imdb_id":iid,"similarity":round(sim,3)}

def enrich_metadata(tv:ET.Element,mappings:list[dict],root:Path,output:Path)->dict:
    omdb_key=os.environ.get("OMDB_API_KEY","").strip(); tmdb_key=os.environ.get("TMDB_API_KEY","").strip()
    max_requests=max(0,int(os.environ.get("METADATA_MAX_REQUESTS",os.environ.get("OMDB_MAX_REQUESTS","150")) or 150)); timeout=max(3,int(os.environ.get("METADATA_TIMEOUT",os.environ.get("OMDB_TIMEOUT","12")) or 12))
    # New cache filename deliberately ignores poisoned v4.1/v4.2 negatives.
    cache_path=root/".cache"/"metadata"/"metadata-v50.json"; cache=_load_cache(cache_path)
    groups={}; allowed=set()
    for row in mappings:
        oid=(row.get("output_tvg_id") or "").strip()
        if oid: allowed.add(oid); groups.setdefault(oid,row.get("group",""))
    stats=Counter(); rows=[]; requests=0; changed=False
    for p in tv.findall("programme"):
        cid=(p.get("channel") or "").strip()
        if cid not in allowed: continue
        stats["programmes_considered"]+=1; title=_text(p,"title")
        if not title: continue
        rating,iid=_existing_imdb(p)
        if rating or iid:
            stats["programmes_with_existing_imdb"]+=1
            if _add_metadata(p,rating,iid): stats["existing_metadata_normalized"]+=1
            continue
        if _skip_generic_metadata_title(title): stats["generic_schedule_blocks_skipped"]+=1; continue
        if not _is_fiction_candidate(p, groups.get(cid, "")):
            stats["non_fiction_skipped"] += 1
            continue
        typ=_media_type(p,groups.get(cid,""))
        if not typ: stats["not_movie_or_series"]+=1; continue
        if len(normalize_name(title))<3: stats["title_too_short"]+=1; continue
        year=_year(p); provider_language=_programme_language(p,title)
        detected_language=_detect_metadata_language(title, provider_language)
        if _skip_metadata_language(provider_language, title):
            stats["non_ru_en_titles_skipped"] += 1
            if detected_language == "uk":
                stats["ukrainian_titles_skipped"] += 1
            elif detected_language == "unknown":
                stats["ambiguous_language_titles_skipped"] += 1
            else:
                stats[f"{detected_language}_titles_skipped"] += 1
            continue
        language = "ru-RU" if detected_language == "ru" else "en-US"
        effective_type = _effective_metadata_type(title, typ)
        canonical_title = _canonical_metadata_title(title, effective_type)
        if normalize_name(canonical_title) != normalize_name(_clean_search_title(title)):
            stats["episode_titles_collapsed"] += 1
        if effective_type != typ:
            stats["multipart_movies_reclassified"] += 1
        key=_cache_key(canonical_title,year,effective_type,language); entry=cache.get(key); source="cache"
        if entry is not None: stats["cache_hits"]+=1
        elif requests>=max_requests: stats["lookup_not_attempted"]+=1; continue
        else:
            try:
                if tmdb_key:
                    entry=_tmdb_lookup_imdb(tmdb_key,canonical_title,year,effective_type,language,timeout,raw_title=title); requests+=1; stats["tmdb_requests"]+=1; source="tmdb"
                    if entry.get("status")=="found":
                        stats["tmdb_matches"]+=1; imdb_rating=""
                        if omdb_key and requests<max_requests:
                            op=_omdb_lookup_id(omdb_key,entry["imdb_id"],timeout); requests+=1; stats["omdb_id_requests"]+=1
                            if str(op.get("Response","")).lower()=="true":
                                imdb_rating=str(op.get("imdbRating","")).strip(); imdb_rating="" if imdb_rating.upper()=="N/A" else imdb_rating
                        entry["imdb_rating"]=imdb_rating; entry["resolver"]="tmdb+omdb" if omdb_key else "tmdb"
                    else:
                        stats[f"tmdb_{entry.get('status','other')}"]+=1; entry["resolver"]="tmdb"
                elif omdb_key:
                    entry=_validate_omdb_payload(_omdb_lookup_title(omdb_key,title,year,typ,timeout),title,year,typ); requests+=1; stats["omdb_title_requests"]+=1; entry["resolver"]="omdb-title"; source="omdb-title"
                else:
                    stats["lookup_not_attempted"]+=1; continue
                cache[key]=entry; changed=True; time.sleep(0.03)
            except Exception as exc:
                stats["api_errors"]+=1
                rows.append({"channel_id":cid,"title":title,"year":year,"type":typ,"status":"api_error","source":"metadata-api","imdb_id":"","imdb_rating":"","detail":str(exc)[:180]}); continue
        if entry and entry.get("status")=="found":
            rating=str(entry.get("imdb_rating","")).strip(); iid=str(entry.get("imdb_id","")).strip()
            if _add_metadata(p,rating,iid): stats["programmes_enriched"]+=1
            stats["metadata_matches"]+=1
            rows.append({"channel_id":cid,"title":title,"year":year,"type":typ,"status":"enriched","source":entry.get("resolver",source),"imdb_id":iid,"imdb_rating":rating,"detail":f"query={entry.get('query_title',title)}; lang={entry.get('language',language)}; attempt={entry.get('attempt','')}; tmdb_title={entry.get('title','')}"})
        elif entry:
            stats[f"cache_{entry.get('status','other')}"]+=1
            rows.append({"channel_id":cid,"title":title,"year":year,"type":typ,"status":entry.get("status","other"),"source":entry.get("resolver",source),"imdb_id":entry.get("imdb_id",""),"imdb_rating":entry.get("imdb_rating",""),"detail":f"query={entry.get('query_title',_clean_search_title(title))}; lang={entry.get('language',language)}; attempts={entry.get('attempts','')}"})
    if changed: _save_cache(cache_path,cache)
    unique={}
    for row in rows: unique[(row["title"],row["year"],row["type"],row["status"])]=row
    report_rows=list(unique.values())
    return {"summary":{"mode":"existing-imdb+tmdb-localized-cascade-v5.0-fiction-multipart+omdb-rating","tmdb_configured":bool(tmdb_key),"omdb_configured":bool(omdb_key),"max_api_requests_per_run":max_requests,"cache_entries":len(cache),**{k:int(v) for k,v in stats.items()},"unique_report_rows":len(report_rows)},"rows":report_rows}
