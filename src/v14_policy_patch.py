from __future__ import annotations
import re

from . import config as _config
from . import metadata_enrichment as _me

_ORIG_LOAD_ALIASES = _config.load_aliases
_ORIG_IS_FICTION = _me._is_fiction_candidate
_ORIG_MEDIA_TYPE = _me._media_type
_ORIG_CLEAN_TITLE = _me._clean_search_title
_ORIG_CANONICAL = _me._canonical_metadata_title

V14_SOURCE_PINS = [
    # Exact distinct HD feed: never collapse to "Наш Кинопоказ".
    {"enabled":"1","playlist_name":"Наш Кинопоказ HD","source":"iptvx-noarch",
     "source_id":"nash-kinopokaz-hd","hard_pin":"1","notes":"v14 exact dedicated HD schedule"},
    # Russian feed, never the UA identity.
    {"enabled":"1","playlist_name":"Наше любимое кино","source":"iptv-online-primary",
     "source_id":"Xnashe-lubimoe","hard_pin":"1","notes":"v14 Russian schedule; never UA"},
    # Force a non-Ukrainian schedule source for KinoSweet.
    {"enabled":"1","playlist_name":"KinoSweet HD","source":"openbox-tsd",
     "source_id":"kinosweet","hard_pin":"1","notes":"v14 Russian-language schedule priority"},
    {"enabled":"1","playlist_name":"Kinosweet HD","source":"openbox-tsd",
     "source_id":"kinosweet","hard_pin":"1","notes":"v14 spelling alias"},
    {"enabled":"1","playlist_name":"Kinosweet","source":"openbox-tsd",
     "source_id":"kinosweet","hard_pin":"1","notes":"v14 spelling alias"},
    # Missing MM schedule.
    {"enabled":"1","playlist_name":"MM USSR Сказки HD","source":"iptvx-noarch",
     "source_id":"minimax-ussr-skazki","hard_pin":"1","notes":"v14 verified current EPG"},
    # 4ever family - exact members, no family collapsing.
    {"enabled":"1","playlist_name":"4ever Cinema","source":"iptvx-noarch","source_id":"4ever-cinema","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Cinema HD","source":"iptvx-noarch","source_id":"4ever-cinema","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Drama","source":"iptvx-noarch","source_id":"4ever-drama","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Drama HD","source":"iptvx-noarch","source_id":"4ever-drama","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Theater","source":"iptvx-noarch","source_id":"4ever-theater","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Theater HD","source":"iptvx-noarch","source_id":"4ever-theater","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Music","source":"iptvx-noarch","source_id":"4ever-music","hard_pin":"1","notes":"v14"},
    {"enabled":"1","playlist_name":"4ever Music HD","source":"iptvx-noarch","source_id":"4ever-music","hard_pin":"1","notes":"v14"},
    # Voen TV is new; try known common IDs without hard-locking the source.
    {"enabled":"1","playlist_name":"Воен ТВ HD","source_id":"Воен ТВ HD","hard_pin":"0","notes":"v14 candidate"},
    {"enabled":"1","playlist_name":"Воен ТВ HD","source_id":"voen-tv-hd","hard_pin":"0","notes":"v14 candidate"},
    {"enabled":"1","playlist_name":"Воен ТВ HD","source_id":"voen-tv","hard_pin":"0","notes":"v14 candidate"},
]

def load_aliases_v14():
    rows=list(_ORIG_LOAD_ALIASES())
    rows.extend(V14_SOURCE_PINS)
    return rows

_config.load_aliases = load_aliases_v14

# Strong series forms only. Parentheses are NOT globally treated as episodes.
_SERIES_PREFIX = re.compile(r"(?i)^\s*(?:т\s*/\s*с|сериал|мультсериал)\b")
_EPISODE_SUFFIX = re.compile(
    r"(?ix)(?:[,.;:\-–—]?\s*)"
    r"(?:"
    r"(?:серия|сер\.?|эпизод|episode|ep\.?)\s*\d{1,4}"
    r"|\d{1,4}\s*(?:с|сер\.?|серия)"
    r"|(?:сезон|season)\s*\d{1,3}(?:\s*[,.;:\-–—]?\s*(?:серия|эпизод|episode)\s*\d{1,4})?"
    r"|s\d{1,2}\s*e\d{1,4}"
    r")\s*$"
)
_KNOWN_PARENT_EPISODE = {"три кота","простоквашино"}

def _parenthetical_known_series(title: str) -> bool:
    value=(title or "").strip()
    m=re.match(r"^(.{3,80}?)\s*\(([^()]{2,120})\)\s*$", value)
    if not m: return False
    inside=m.group(2).strip()
    # A year in parentheses is a movie/year marker, never an episode here.
    if re.fullmatch(r"(?:19|20)\d{2}", inside): return False
    return m.group(1).strip().lower() in _KNOWN_PARENT_EPISODE

def is_fiction_v14(programme, group):
    title=_me._text(programme,"title").strip()
    if _SERIES_PREFIX.search(title) or _EPISODE_SUFFIX.search(title) or _parenthetical_known_series(title):
        return True
    return _ORIG_IS_FICTION(programme,group)

def media_type_v14(programme, group):
    title=_me._text(programme,"title").strip()
    if _SERIES_PREFIX.search(title) or _EPISODE_SUFFIX.search(title) or _parenthetical_known_series(title):
        return "series"
    return _ORIG_MEDIA_TYPE(programme,group)

def clean_title_v14(title: str) -> str:
    raw=(title or "").strip()
    x=_ORIG_CLEAN_TITLE(raw)
    # Strip explicit series prefix.
    x=re.sub(r"(?i)^\s*(?:т\s*/\s*с|сериал|мультсериал)\s*[:.\-–—]?\s*","",x).strip()
    # Collapse trailing season/episode markers.
    x=_EPISODE_SUFFIX.sub("",x).strip(" -–—:;,.")
    # Known animation series: "Три кота (Картинная галерея)" -> "Три кота".
    if _parenthetical_known_series(raw):
        x=raw.split("(",1)[0].strip(" -–—:;,.")
    return re.sub(r"\s+"," ",x).strip() or raw

def canonical_v14(title: str, media_type: str) -> str:
    base=clean_title_v14(title)
    if media_type=="series":
        # For strong/known series, episode subtitle in parentheses is not identity.
        if _parenthetical_known_series(title):
            return base
    return _ORIG_CANONICAL(base,media_type)

_me._is_fiction_candidate=is_fiction_v14
_me._media_type=media_type_v14
_me._clean_search_title=clean_title_v14
_me._canonical_metadata_title=canonical_v14
