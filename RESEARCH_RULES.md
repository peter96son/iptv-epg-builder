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


## XMLTV timestamp resilience (added after live run #2)

- External XMLTV feeds are untrusted data and may contain malformed or non-standard timestamps.
- One malformed `start`/`stop` value must NEVER abort the whole EPG build.
- Timestamp conversion must use fixed-width field parsing rather than relying on `strptime` variable-width directive behavior.
- Tolerate `24:00:00` by rolling to the next day.
- Tolerate leap-second style `...60` seconds by normalization.
- If a timestamp still cannot be safely interpreted, preserve the original timestamp verbatim and continue.
- Freshness checks should fail closed for malformed dates, while timestamp conversion should fail open by preserving the original value.
- Live run #2 on 2026-08-16 exposed this requirement: the build failed inside `convert_xmltv_timestamp` with `ValueError: unconverted data remains: 0`.


## UHF companion playlist (v1.2)

- The daily user-facing playlist should be `output/playlist-uhf.m3u`, not the private provider M3U directly.
- `playlist-uhf.m3u` points its EPG header to `output/epg.xml.gz`.
- Generated M3U and XMLTV must use the same final TVG IDs.
- Preserve provider stream URLs, channel order, names, logos and `#EXTGRP` categories exactly.
- Do not publish or embed private `PLAYLIST_URL`; it remains a GitHub Secret.
- Rewrite a `tvg-id` only when a final EPG mapping is known.
- Unmatched channels remain otherwise unchanged.
- IPTV Online primary EPG is not automatically ground truth; correctness auditing is a separate quality phase.


## Playlist evolution and safety (v1.3)

- Provider channel changes are expected; always rebuild from the latest private M3U.
- New channels must be accepted automatically unless a global safety rule is triggered.
- A drop of more than 15% of channel count versus the last successful snapshot is treated as a likely provider/error outage and must stop publication.
- Keep `playlist-snapshot.json` as the last successful structural baseline.
- Keep `playlist-changes.json` as the machine-readable diff.
- Keep `history.json` for trend analysis.
- Dashboard output is informational only; it must never alter matching decisions.


## Privacy rule for UHF delivery (v1.4)

- Never publish an M3U containing actual provider stream URLs in a public repository.
- Public GitHub output is limited to EPG, safe TVG-ID mappings and diagnostics.
- Private M3U delivery is performed by Cloudflare Worker with encrypted secrets.
- Treat the Worker bearer URL as a credential. Rotate `ACCESS_TOKEN` if it leaks.
- `PLAYLIST_URL` must never appear in public output.
