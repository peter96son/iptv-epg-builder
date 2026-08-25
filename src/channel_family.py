from __future__ import annotations
from .utils import normalize_name

REGION_TOKENS = {
    "RU":{"ru","rus","russia","russian","россия"},"UA":{"ua","ukraine","ukr","украина","україна"},
    "BY":{"by","belarus","bel","беларусь"},"GB":{"uk","gb","britain","british","united kingdom"},
    "US":{"us","usa","united states"},"CA":{"ca","canada","canadian"},"DE":{"de","deu","germany","deutsch","deutschland"},
    "AT":{"at","austria","osterreich","oesterreich"},"IT":{"it","italy","italia"},"RO":{"ro","romania","romanian","românia"},
    "BG":{"bg","bulgaria","bulgarian"},"PL":{"pl","poland","polska","polish"},"HU":{"hu","hungary","magyar"},
    "CZ":{"cz","czech","cesko","česko"},"SK":{"sk","slovakia","slovensko"},"GR":{"gr","greece","greek"},
    "TR":{"tr","turkey","turkiye","türkiye","tur"},"HR":{"hr","croatia","croatian"},"LT":{"lt","lithuania","lithuanian"},
    "LV":{"lv","latvia","latvian"},"IL":{"il","israel","israeli"},"MD":{"md","moldova","moldavian"},
    "GE":{"ge","georgia","georgian"},"AM":{"am","armenia","armenian"},"AZ":{"az","azerbaijan","azerbaijani"},
}
_GENERIC_REGIONAL_WORDS={"europe","europa","euro","international","intl","global"}
_DELIVERY_SUFFIXES={"hd","fhd","uhd","4k","hevc","h265","h264"}

def _token_variants(region):
    if not region: return set()
    region=region.upper()
    if "/" in region:
        out=set()
        for part in region.split("/"): out.update(_token_variants(part))
        return out
    return {normalize_name(x) for x in REGION_TOKENS.get(region,set()) if normalize_name(x)}

def family_candidates(name, region):
    normalized=normalize_name(name)
    if not normalized: return []
    candidates=[normalized]
    removable=_token_variants(region)|_GENERIC_REGIONAL_WORDS
    def add(tokens):
        v=" ".join(tokens).strip()
        if v and v not in candidates: candidates.append(v)
    tokens=normalized.split()
    work=list(tokens)
    changed=True
    while changed and work:
        changed=False
        if work and work[0] in removable: work.pop(0); changed=True
        if work and work[-1] in removable: work.pop(); changed=True
    add(work)
    quality=list(tokens)
    while quality and quality[-1] in _DELIVERY_SUFFIXES: quality.pop()
    add(quality)
    combo=list(quality); changed=True
    while changed and combo:
        changed=False
        if combo and combo[0] in removable: combo.pop(0); changed=True
        if combo and combo[-1] in removable: combo.pop(); changed=True
    add(combo)
    return candidates
