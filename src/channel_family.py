from __future__ import annotations
from .utils import normalize_name

REGION_TOKENS = {
    "RU": {"ru","rus","russia","russian","россия"},
    "UA": {"ua","ukraine","ukr","украина","україна"},
    "BY": {"by","belarus","bel","беларусь"},
    "GB": {"uk","gb","britain","british","united kingdom"},
    "US": {"us","usa","united states"},
    "CA": {"ca","canada","canadian"},
    "DE": {"de","deu","germany","deutsch","deutschland"},
    "AT": {"at","austria","osterreich","oesterreich"},
    "IT": {"it","italy","italia"},
    "RO": {"ro","romania","romanian","românia"},
    "BG": {"bg","bulgaria","bulgarian"},
    "PL": {"pl","poland","polska","polish"},
    "HU": {"hu","hungary","magyar"},
    "CZ": {"cz","czech","cesko","česko"},
    "SK": {"sk","slovakia","slovensko"},
    "GR": {"gr","greece","greek"},
    "TR": {"tr","turkey","turkiye","türkiye","tur"},
    "HR": {"hr","croatia","croatian"},
    "LT": {"lt","lithuania","lithuanian"},
    "LV": {"lv","latvia","latvian"},
    "IL": {"il","israel","israeli"},
    "MD": {"md","moldova","moldavian"},
    "GE": {"ge","georgia","georgian"},
    "AM": {"am","armenia","armenian"},
    "AZ": {"az","azerbaijan","azerbaijani"},
}
_GENERIC_REGIONAL_WORDS={"europe","europa","euro","international","intl","global"}

def _token_variants(region: str) -> set[str]:
    if not region: return set()
    region=region.upper()
    if "/" in region:
        out=set()
        for part in region.split("/"): out.update(_token_variants(part))
        return out
    return {normalize_name(x) for x in REGION_TOKENS.get(region,set()) if normalize_name(x)}

def family_candidates(name: str, region: str) -> list[str]:
    """Only strip explicit region markers. HD/FHD/UHD/4K are NEVER stripped here."""
    normalized=normalize_name(name)
    if not normalized: return []
    candidates=[normalized]
    tokens=normalized.split()
    removable=_token_variants(region)|_GENERIC_REGIONAL_WORDS
    changed=True
    work=list(tokens)
    while changed and work:
        changed=False
        if work and work[0] in removable:
            work.pop(0); changed=True
        if work and work[-1] in removable:
            work.pop(); changed=True
    stripped=" ".join(work).strip()
    if stripped and stripped!=normalized:
        candidates.append(stripped)
    for marker in sorted(removable,key=len,reverse=True):
        if " " not in marker: continue
        if normalized.endswith(" "+marker):
            v=normalized[:-(len(marker)+1)].strip()
            if v and v not in candidates: candidates.append(v)
        if normalized.startswith(marker+" "):
            v=normalized[len(marker)+1:].strip()
            if v and v not in candidates: candidates.append(v)
    return candidates
