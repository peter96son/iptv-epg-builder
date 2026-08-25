from __future__ import annotations

import os
import re

from . import metadata_backfill as _mb
from .utils import normalize_name

_ORIGINAL_BUILD_QUEUE = _mb.build_queue
_ORIGINAL_ENRICH = _mb.enrich_metadata

# Provider/EPG placeholders that are not actual works.
_GENERIC_RE = re.compile(
    r"""(?ix)^\s*(?:
        сезон\s*\d+\s*[,.:;\-–—]?\s*(?:эпизод|епізод|серия|серія)\s*\d+
      | (?:эпизод|епізод|серия|серія)\s*\d+
      | программа\s+(?:отсутствует|недоступна)
      | програма\s+(?:відсутня|недоступна)
      | програма\s+відсутня\s+або\s+її\s+немає
      | no\s+(?:programme|program|epg)
      | программа\s+передач
      | телепрограмма
    )\s*$"""
)

# The generated EPG may already contain our own display decoration.
# It must NEVER be sent back to TMDb as part of a search query.
_IMDB_SUFFIX_RE = re.compile(
    r"""(?ix)
    \s*
    (?:[·•|]\s*)?
    imdb
    \s*(?:rating|рейтинг)?\s*
    (?:[:=]\s*)?
    \d{1,2}(?:[.,]\d+)?
    (?:\s*/\s*10)?
    \s*$
    """
)
_TRAILING_YEAR_RE = re.compile(
    r"""\s*[\[(]\s*(19\d{2}|20\d{2})\s*(?:год|р\.?)?\s*[\])]\s*$""",
    re.I,
)

# Strong Ukrainian markers. Backfill intentionally targets RU/EN metadata; these
# are skipped BEFORE any TMDb request instead of being mislabelled en-US.
_UK_CHARS_RE = re.compile(r"[іїєґІЇЄҐ]")
_UK_WORD_RE = re.compile(
    r"""(?ix)\b(?:
      програма|фільм|війна|дівчина|жінка|чоловік|кохання|мисливці|смерті|
      відважні|незнайомець|танцювальні|дещо|моєму|світі|будинку|дім|її
    )\b"""
)

def _clean_backfill_title(title: str, year: str) -> tuple[str,str]:
    value=(title or "").strip()

    # Strip our own "· IMDb 7.1" / "IMDb 7.1" decoration first.
    value=_IMDB_SUFFIX_RE.sub("",value).strip(" \t-–—·•|")

    # A display title may be "Title (2024)" even though <date> already supplied
    # the same year. Keep year as a separate resolver key.
    m=_TRAILING_YEAR_RE.search(value)
    if m:
        if not year:
            year=m.group(1)
        value=value[:m.start()].strip(" \t-–—:;,.")

    value=re.sub(r"\s+"," ",value).strip()
    return value,year

def _skip_row(title: str) -> bool:
    value=(title or "").strip()
    if not value or len(value)<2:
        return True
    if _GENERIC_RE.match(value):
        return True
    if _UK_CHARS_RE.search(value) or _UK_WORD_RE.search(value):
        return True
    return False

def smart_build_queue(tv,mappings):
    raw=_ORIGINAL_BUILD_QUEUE(tv,mappings)

    # Re-key after cleanup so "Веном", "Веном (2018)" and
    # "Веном (2018) · IMDb 6.6" collapse into one work.
    merged={}
    skipped_generic=0
    skipped_uk=0

    for row in raw:
        row=dict(row)
        title,year=_clean_backfill_title(row.get("title",""),row.get("year",""))

        if _GENERIC_RE.match(title or ""):
            skipped_generic+=1
            continue
        if _UK_CHARS_RE.search(title or "") or _UK_WORD_RE.search(title or ""):
            skipped_uk+=1
            continue
        if _skip_row(title):
            skipped_generic+=1
            continue

        row["title"]=title
        row["year"]=year
        key=(normalize_name(title),year,row.get("type",""),row.get("language",""))

        old=merged.get(key)
        if old is None:
            merged[key]=row
            continue

        old["occurrences"]=int(old.get("occurrences") or 0)+int(row.get("occurrences") or 0)
        old["future_occurrences"]=int(old.get("future_occurrences") or 0)+int(row.get("future_occurrences") or 0)
        old["channel_count"]=max(int(old.get("channel_count") or 0),int(row.get("channel_count") or 0))
        old["priority"]=min(int(old.get("priority") or 9),int(row.get("priority") or 9))

    out=list(merged.values())
    out.sort(key=lambda r:(
        int(r.get("priority") or 0),
        -int(r.get("future_occurrences") or 0),
        -int(r.get("occurrences") or 0),
        r.get("group",""),r.get("title",""),r.get("year",""),
    ))
    print(
        f"[backfill-v13.25] queue raw={len(raw)} clean={len(out)} "
        f"generic_skipped={skipped_generic} uk_skipped={skipped_uk}",
        flush=True,
    )
    return out

def lean_enrich(*args,**kwargs):
    # Original backfill sets this to 1 immediately before calling enrich_metadata.
    # Override it here: nightly work should cover more unique titles rather than
    # spend ~5 alternative TMDb requests on one low-probability candidate.
    previous=os.environ.get("METADATA_MULTI_FALLBACK")
    os.environ["METADATA_MULTI_FALLBACK"]="0"
    try:
        return _ORIGINAL_ENRICH(*args,**kwargs)
    finally:
        if previous is None:
            os.environ.pop("METADATA_MULTI_FALLBACK",None)
        else:
            os.environ["METADATA_MULTI_FALLBACK"]=previous

def main():
    _mb.build_queue=smart_build_queue
    _mb.enrich_metadata=lean_enrich
    return _mb.main()

if __name__=="__main__":
    raise SystemExit(main())
