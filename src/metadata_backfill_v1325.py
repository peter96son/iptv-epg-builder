from __future__ import annotations
import os,re
from . import title_normalization_patch  # noqa: F401
from . import metadata_backfill as _mb
from . import metadata_enrichment as _me
from .utils import normalize_name

_ORIGINAL_BUILD_QUEUE=_mb.build_queue
_ORIGINAL_ENRICH=_mb.enrich_metadata
_GENERIC_RE=re.compile(r"""(?ix)^\s*(?:сезон\s*\d+\s*[,.:;\-–—]?\s*(?:эпизод|эпізод|серия|серія)\s*\d+|(?:эпизод|эпізод|серия|серія)\s*\d+|программа\s+(?:отсутствует|недоступна)|програма\s+(?:відсутня|недоступна)|програма\s+відсутня\s+або\s+її\s+немає|no\s+(?:programme|program|epg)|программа\s+передач|телепрограмма)\s*$""")
_IMDB_SUFFIX_RE=re.compile(r"""(?ix)\s*(?:[·•|]\s*)?imdb\s*(?:rating|рейтинг)?\s*(?:[:=]\s*)?\d{1,2}(?:[.,]\d+)?(?:\s*/\s*10)?\s*$""")
_TRAILING_YEAR_RE=re.compile(r"""\s*[\[(]\s*(19\d{2}|20\d{2})\s*(?:год|р\.?)?\s*[\])]\s*$""",re.I)
_UK_CHARS_RE=re.compile(r"[іїєґІЇЄҐ]")
_UK_WORD_RE=re.compile(r"""(?ix)\b(?:програма|фільм|війна|дівчина|жінка|чоловік|кохання|мисливці|смерті|відважні|незнайомець|танцювальні|дещо|моєму|світі|будинку|дім|її)\b""")

def _clean_backfill_title(title,year):
    value=(title or "").strip()
    value=_IMDB_SUFFIX_RE.sub("",value).strip(" \t-–—·•|")
    m=_TRAILING_YEAR_RE.search(value)
    if m:
        if not year: year=m.group(1)
        value=value[:m.start()].strip(" \t-–—:;,.")
    value=_me._clean_search_title(value)
    return re.sub(r"\s+"," ",value).strip(),year

def _skip_row(title):
    value=(title or "").strip()
    return (not value or len(value)<2 or bool(_GENERIC_RE.match(value))
            or bool(_UK_CHARS_RE.search(value)) or bool(_UK_WORD_RE.search(value)))

def smart_build_queue(tv,mappings):
    raw=_ORIGINAL_BUILD_QUEUE(tv,mappings); merged={}
    skipped_generic=skipped_uk=0
    for row in raw:
        row=dict(row)
        title,year=_clean_backfill_title(row.get("title",""),row.get("year",""))
        if _GENERIC_RE.match(title or ""): skipped_generic+=1; continue
        if _UK_CHARS_RE.search(title or "") or _UK_WORD_RE.search(title or ""): skipped_uk+=1; continue
        if _skip_row(title): skipped_generic+=1; continue
        row["title"]=title; row["year"]=year
        # The cumulative title-normalization policy is authoritative for series identity.
        fake_title=row["title"]
        if re.search(r"(?i)(?:\d+\s*(?:с|сер\.?|серия)|сезон\s*\d+|s\d{1,2}\s*e\d+)\s*$", fake_title):
            row["type"]="series"
        key=(normalize_name(title),year,row.get("type",""),row.get("language",""))
        old=merged.get(key)
        if old is None: merged[key]=row; continue
        old["occurrences"]=int(old.get("occurrences") or 0)+int(row.get("occurrences") or 0)
        old["future_occurrences"]=int(old.get("future_occurrences") or 0)+int(row.get("future_occurrences") or 0)
        old["channel_count"]=max(int(old.get("channel_count") or 0),int(row.get("channel_count") or 0))
        old["priority"]=min(int(old.get("priority") or 9),int(row.get("priority") or 9))
    out=list(merged.values())
    out.sort(key=lambda r:(int(r.get("priority") or 0),-int(r.get("future_occurrences") or 0),-int(r.get("occurrences") or 0),r.get("group",""),r.get("title",""),r.get("year","")))
    print(f"[backfill-v14] queue raw={len(raw)} clean={len(out)} generic_skipped={skipped_generic} uk_skipped={skipped_uk}",flush=True)
    return out

def lean_enrich(*args,**kwargs):
    prev=os.environ.get("METADATA_MULTI_FALLBACK")
    os.environ["METADATA_MULTI_FALLBACK"]="0"
    try: return _ORIGINAL_ENRICH(*args,**kwargs)
    finally:
        if prev is None: os.environ.pop("METADATA_MULTI_FALLBACK",None)
        else: os.environ["METADATA_MULTI_FALLBACK"]=prev

def main():
    _mb.build_queue=smart_build_queue
    _mb.enrich_metadata=lean_enrich
    return _mb.main()

if __name__=="__main__":
    raise SystemExit(main())
