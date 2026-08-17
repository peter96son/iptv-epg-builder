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


## IPTV Online format facts (confirmed 2026-08-16)

- The live IPTV Online M3U uses `#EXTGRP:<category>` on a separate line after `#EXTINF`.
- Do not assume `group-title="..."` is present.
- Parser must support both formats; `#EXTGRP` overrides `group-title` when both exist.
- Confirmed provider categories include:
  - Россия
  - Украинские
  - Кино
  - Кинозалы
  - Кинозалы UA
  - Кино 4K
  - Спорт
  - Познавательные
  - Детские
  - Разное
  - Новости
  - Музыкальные
  - Беларусь
  - Литва
  - Латвия
  - and additional country/category groups lower in the playlist.
- Preserve provider category names exactly in reports; do not invent replacements unless making a separate normalized analytical field.

## Measurement rules

- Baseline = channels with fresh programme data from the IPTV Online primary EPG, not channels merely carrying `tvg-id`.
- Final = channels with fresh programme data after all fallbacks.
- Improvement = `final - baseline`.
- Movie priority reporting must aggregate: `Кино`, `Кино 4K`, `Кинозалы`, `Кинозалы UA`.
- Every run should report total/baseline/final/added/coverage percentage by provider category.
- A source's usefulness is measured by the number of *previously unresolved* channels it adds.
- Keep the latest `output/unmatched.csv` as the canonical research queue.

## Current measured baseline from first successful live run

- Playlist channels: 2700
- Primary EPG matched with fresh programmes: 1632
- Final after fallbacks: 2097
- Added by fallbacks: 465
- Unmatched: 603
- Total programme entries generated: 308901
- Biggest fallback contributors in that run:
  - Gabbarit: +249
  - iptvX: +203
  - EPG.pw Lite: +7
  - Runigma: +3
  - AnZo: +3

Do not treat these figures as permanent. They are a historical checkpoint; use each new `status.json` as the source of truth.
