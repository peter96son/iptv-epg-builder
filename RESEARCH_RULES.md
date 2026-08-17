# Research rules

1. Never report an EPG improvement from `tvg-id` presence alone.
2. A channel counts as covered only when fresh `<programme>` entries exist.
3. Movie channels and movie channel families are research priority #1, but the production guide covers the whole playlist.
4. Preferred languages: Russian, Ukrainian, Belarusian, English, German, Dutch.
5. Language is a prioritization signal, not an exclusion rule. Research any provider country group when it can safely recover real EPG coverage. Country/region correctness outranks language preference.
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
- Current Worker route is `/tv`; `ACCESS_TOKEN` is no longer used. Keep `PLAYLIST_URL` secret and never publish provider stream URLs.
- `PLAYLIST_URL` must never appear in public output.


## v1.7 mainstream regional recovery (2026-08-17)

- Research normal broadcast channels before speculative FAST/virtual families.
- Use country-specific XMLTV catalogs to verify aliases.
- Every v1.7 alias is constrained by `provider_group`, `region`, and `source`.
- HD/SD aliases are permitted only for the same underlying linear service when the source catalog exposes one schedule.
- A missing country-specific channel is NOT permission to borrow another country's schedule.
- Confirmed example: `Discovery Science HD RO` is present in the provider's Romania group but is absent from the checked EPGShare RO catalog as of 2026-08-17. Keep it unmatched rather than map to UK `Disc.Science.uk` or another region.
- v1.7 verified recovery batches: Italy RAI, UK ITV/Sky Cinema, Romania ProTV/TVR and selected mainstream services, Bulgaria Diema/Nova/BNT/Planeta/SKAT.

## Russian/CIS recovery policy (v1.8)

- Russian-language recovery is NOT limited to the provider group `Россия`.
- Search the entire unmatched queue, especially topical groups: `Кино`, `Кино 4K`, `Кинозалы`, `Кинозалы UA`, `Музыкальные`, `Познавательные`, `Детские`, `Новости`, `Спорт`, `Разное`.
- Provider country/group remains part of channel identity. Same-name channels in different countries must not be merged automatically.
- For regional-sensitive brands (Discovery, TLC, Eurosport, Viasat, HBO, Nickelodeon, Disney, MTV, etc.) require a compatible regional source or an explicitly verified alias.
- Treat +1/+2/+3/+4/+7 and other time-shift variants as different schedules unless verified otherwise.
- DITV, VeleS, Play-X, KLI, BCU, Joker, Clarity and similar virtual/FAST families are excluded from generic automatic recovery. They require a dedicated feed or verified per-channel mapping.
- `output/unmatched-russian-cis.*` is the canonical Russian/CIS research queue starting with v1.8.
- `epgone-ru2` is a fallback source only. It may add a channel only when fresh programme data exists and normal matching/region safety rules pass.

## v1.9 player-visible coverage rule

- `mapping.csv` is not proof that the user will see guide data.
- Final validation must inspect the actual programmes emitted for each `output_tvg_id`.
- A channel needs at least one current/upcoming programme; stale entries alone do not count.
- If a primary source has stale-only data for a channel, do not resolve it there; allow later fallbacks to try.
- `output/postbuild-gaps.csv` is the canonical queue for channels that matched structurally but failed final guide usability.
- A regression in channel count must be investigated against provider playlist changes and source failures before assuming matcher quality degraded.

## v2.0 end-to-end verification

- Never conclude that a player should have EPG from `mapping.csv` alone.
- First require post-build XMLTV validation (`postbuild-gaps.csv` empty for that channel).
- Then require live Worker validation (`worker-audit-gaps.csv` empty for that channel).
- `?fresh=1` is allowed only for automated diagnostics; users keep `/tv` as their playlist URL.
- If both audits pass but an IPTV player still shows no guide, investigate player refresh/cache/binding before changing the EPG mapping.
- Worker audit is diagnostic and must not delete a known-good EPG merely because the Worker endpoint is temporarily unreachable.

## v2.0 Russian/CIS recovery source

- `teleguide-ru` is an additional broad Russian/CIS fallback sourced from the official teleguide.info XMLTV download.
- It remains below specialized/country-scoped sources and above the final emergency Gabbarit fallback.
- It must pass the same fresh-programme gate as every other source.
- Regional-sensitive global brands still require region-compatible name matching; do not use Teleguide as a reason to weaken that protection.

## v2.1 download resilience and targeted diagnostics

- Large XMLTV downloads must never accept an `IncompleteRead` partial body as a valid feed.
- Retry the complete feed; source-specific retry counts are allowed for flaky large providers.
- Cache-busting on retry is allowed only when explicitly enabled for that source.
- Teleguide uses 5 attempts in v2.1 because live GitHub Actions observed repeated truncated multi-megabyte responses.
- `data/channel-watchlist.json` is the persistent list of channels requiring targeted player/EPG diagnosis.
- Every build writes `output/channel-diagnostics.json` with mapping/source/ID plus current and next programmes for watchlisted channels.
- A channel on the watchlist is not considered diagnosed merely because it is matched; its actual current/upcoming programme records must be shown in the diagnostic output.
- Release ZIPs must not contain generated `output/` files; GitHub Actions owns generated output to avoid merge conflicts.

## v3.0 source resilience and confidence

- Record mapping confidence in `mapping.csv` and post-build validation output.
- Regional family matching is allowed only for known regional-sensitive brands and a compatible region-scoped XMLTV source.
- Persist only explicitly enabled flaky-source caches. A cached XMLTV may be used only after all live retries fail and only within the configured stale-if-error window.
- Cached data must still pass the normal fresh-programme gate; cache fallback never turns stale schedules into valid coverage.
- Generated `output/` files are never shipped in release ZIPs; GitHub Actions owns them.

## v3.1 source-order safety

Never improve coverage by allowing a heuristic/family match to take precedence over an exact or manually verified match available from a later source. Heuristic recovery is a second-pass operation over unresolved channels only. Coverage regressions versus a known-good build must be treated as failures to investigate, not accepted as the cost of a new matching feature.
