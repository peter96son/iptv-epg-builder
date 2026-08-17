# Research rules

1. Never report an EPG improvement from `tvg-id` presence alone.
2. A channel counts as covered only when fresh `<programme>` entries exist.
3. Movie channels and movie channel families are research priority #1, but the production guide covers the whole playlist.
4. Preferred languages: Russian, Ukrainian, Belarusian, English, German, Dutch.
5. Do not spend research time on Romanian/Polish/Hungarian/etc. channels unless the actual channel/EPG is in a preferred language.
6. Do not guess ambiguous channels (`Ужасы HD`, `Детектив HD`, etc.) from a similar name.
7. `no_epg_*` values are dummy IDs and must never be treated as real XMLTV IDs.
8. Conflicting provider IDs must be fixed by exact channel name, not by the broken shared ID.
9. Specialized family EPG sources should outrank broad aggregators when both are live.
10. Any automatic research module may suggest mappings, but only manually approved mappings enter `data/aliases.csv`.
11. Preserve the provider's playlist stream URLs; this project changes guide metadata, not stream endpoints.
12. Pacific time means `America/Los_Angeles`, not a hard-coded UTC-8 offset.
