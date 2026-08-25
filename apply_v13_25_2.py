#!/usr/bin/env python3
from pathlib import Path
p=Path("src/metadata_enrichment.py")
if not p.exists(): raise SystemExit("Run from repository root")
s=p.read_text(encoding="utf-8"); orig=s
s=s.replace('SERIES_WORDS = {"series", "serial", "сериал", "сериалы", "tv series", "episode", "эпизод"}',
'SERIES_WORDS = {"series", "serial", "сериал", "сериалы", "tv series", "episode", "эпизод", "мультсериал", "мультсериалы"}')
anchor='MOVIE_GROUPS = {"Кино", "Кино 4K", "Кинозалы", "Кинозалы UA"}'
extra="""\nKNOWN_EPISODIC_FRANCHISES = {"три кота", "простоквашино"}\n\ndef _known_parenthetical_series(title: str) -> bool:\n    value=(title or "").strip().lower()\n    if "(" not in value or ")" not in value: return False\n    base=value.split("(",1)[0].strip(" .—-")\n    return base in KNOWN_EPISODIC_FRANCHISES\n"""
if "KNOWN_EPISODIC_FRANCHISES" not in s: s=s.replace(anchor,anchor+extra)
s=s.replace('if re.match(r"^\\s*(?:т/с|сериал)\\b", title):\n        return "series"',
            'if re.match(r"^\\s*(?:т\\s*/\\s*с|сериал|мультсериал)\\b", title):\n        return "series"\n    if _known_parenthetical_series(title):\n        return "series"')
s=s.replace('if re.match(r"^\\s*(?:х/ф|т/с|сериал|фильм|кино)\\b", title):',
            'if re.match(r"^\\s*(?:х/ф|т\\s*/\\s*с|сериал|мультсериал|фильм|кино)\\b", title):')
needle='    if programme.find("episode-num") is not None or any(w in joined for w in SERIES_WORDS):\n        return "series"'
replacement='    if re.search(r"(?i)(?:^|[\\\\s.])(?:\\\\d{1,3}\\\\s*(?:с|серия|сер\\\\.?)|сезон\\\\s*\\\\d+|s\\\\d{1,2}\\\\s*e\\\\d{1,3})\\\\s*$", title):\\n        return "series"\\n    if programme.find("episode-num") is not None or any(w in joined for w in SERIES_WORDS):\\n        return "series"'
s=s.replace(needle,replacement)
if s!=orig:
    p.write_text(s,encoding="utf-8"); print("metadata_enrichment.py patched")
else: print("No metadata changes applied (already patched or layout changed)")
print("v13.25.2 patch complete")
