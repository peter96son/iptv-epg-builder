# IPTV EPG Builder v12.0

Current release: **v12.0**. See `RELEASE_NOTES_V12.0.md`.

# IPTV EPG Builder

Personal XMLTV/EPG builder for a large IPTV playlist, optimized first for Russian, Ukrainian, Belarusian, English, German and Dutch channels.

## What it does

- downloads the current M3U playlist at every run;
- downloads multiple XMLTV sources;
- keeps a programme only when the channel has **fresh `<programme>` data**;
- prefers the provider's own `tvg-id`, then researched aliases, then safe exact-name matching;
- treats dummy IDs such as `no_epg_*` as missing;
- supports manually researched channel families such as Magic, KLI, Velilla, BCU, CPS and NEXT through `data/aliases.csv`;
- converts XMLTV timestamps to `America/Los_Angeles`, automatically handling PDT/PST;
- writes a compact `output/epg.xml.gz` for UHF;
- writes `status.json`, `mapping.csv` and `unmatched.csv`;
- refuses to overwrite a healthy guide if the programme count collapses by more than the configured safety threshold.

## Repository structure

```text
.github/workflows/update.yml  GitHub Actions scheduler
src/builder.py                production orchestration
src/matcher.py                safe channel matching
src/xmltv.py                  XMLTV indexing/streaming
src/playlist.py               M3U parser
src/config.py                 config loaders
src/utils.py                  download/time/name helpers
src/research.py               future research assistant
data/sources.json             XMLTV sources
data/aliases.csv              manually verified mappings
data/tvg_id_fixes.csv         fixes for conflicting/broken provider IDs
data/language_scope.json      language research scope
data/priorities.json          priorities and safety thresholds
output/                       generated guide and reports
run.py                        entry point
```

## Required GitHub secret

Create repository secret:

`PLAYLIST_URL`

Its value is your private IPTV playlist URL. Do **not** put the URL into a public file.

Path in GitHub:

`Settings → Secrets and variables → Actions → New repository secret`

## First run

Open:

`Actions → Update EPG → Run workflow`

After the run, inspect:

- `output/status.json`
- `output/mapping.csv`
- `output/unmatched.csv`
- `output/epg.xml.gz`

The useful number is `added_by_fallback_channels`, not the number of channels that merely have an ID.

## UHF

After a successful run, use the raw GitHub URL of:

`output/epg.xml.gz`

as the external EPG source in UHF.

## Safety rule

A channel is never considered covered just because an XMLTV `<channel>` entry exists. It must have fresh programme entries in the configured date window.


## IPTV Online category handling

IPTV Online stores categories using separate `#EXTGRP:` lines rather than relying on `group-title`.
Version 1.1 supports both formats and reports real provider categories in `output/status.json`.

`movie_priority` aggregates the four movie-focused provider categories:

- `Кино`
- `Кино 4K`
- `Кинозалы`
- `Кинозалы UA`


## v1.1.1 timestamp hardening

External XMLTV timestamps are treated as untrusted input. A malformed timestamp
can no longer terminate the whole GitHub Actions run.


## v1.2 — UHF companion playlist

Each successful build also creates `output/playlist-uhf.m3u`.

It preserves provider stream URLs, ordering, logos, names and `#EXTGRP`
categories while pointing UHF to the merged EPG and aligning verified TVG IDs.

Public URLs after a successful run:

- Playlist: `https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/playlist-uhf.m3u`
- EPG: `https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/epg.xml.gz`

The private IPTV Online playlist URL stays only in the GitHub Secret.


## v1.3 — reliability, changes and history

New generated files:

- `output/playlist-snapshot.json`
- `output/playlist-changes.json`
- `output/history.json`
- `output/dashboard.md`
- `output/dashboard.html`

The builder now rejects suspicious playlist collapses (>15% fewer channels than the last successful snapshot) and tracks new/removed/renamed/moved channels and changed stream URLs.


## v1.4 — private UHF delivery

The repository no longer publishes a stream-bearing M3U.

GitHub publishes `output/epg.xml.gz` and `output/uhf-mapping.json`.
The private playlist is generated on demand by the Worker in `cloudflare-worker/`.
Store `PLAYLIST_URL` as a Cloudflare Worker secret. The current Worker uses the permanent `/tv` route and does not require `ACCESS_TOKEN`.

## v1.5 — family-first unmatched analysis

Version 1.5 adds automatic diagnostics for the remaining unmatched channels. Every successful build writes:

- `output/unmatched-families.json`
- `output/unmatched-families.csv`
- `output/unmatched-families.md`

The reports group known FAST/virtual/cinema families such as DITV, VeleS, Magic, KLI, Play-X, BCU, Joker and Clarity so research can be done family-by-family instead of channel-by-channel.

This is deliberately **diagnostic only**. The classifier never creates an EPG mapping and never fuzzy-matches a channel into the live guide.

Cloudflare Worker v1.5.0 routes:

- `/tv` — permanent IPTV-player URL;
- `/download` — download the rewritten playlist as `playlist.m3u`;
- `/epg` — EPG redirect;
- `/health` — health check.

The Worker understands IPTV Online's separate `#EXTGRP:` lines and strips unsafe EPG hints from unmatched movie/FAST channels. Dummy `no_epg_*` IDs are also removed.

## v1.6: region-aware EPG matching

v1.6 treats the IPTV.online provider group as country/region context. International channel brands can no longer be matched by display name to an XMLTV source from the wrong country. Country-scoped EPGShare feeds were added for several previously weak regions. Persistent matching rules are in `MATCHING_POLICY.md`.


### v1.7
Adds verified country-constrained aliases for mainstream channels in Italy, UK, Romania and Bulgaria. These mappings are source-specific and cannot silently cross regions.

## v1.9 Russian/CIS recovery

v1.9 adds a Russian-language EPG.ONE fallback and a dedicated Russian/CIS unmatched research queue. The queue scans topical categories as well as country groups, because Russian-language channels are not confined to `Россия`. It remains diagnostic and does not weaken region-aware or virtual-channel safety rules.


## v1.9

v1.9 adds player-visible post-build validation. The builder no longer treats a channel as covered merely because a source contains a matching ID/name and some recent-date XMLTV data. The source must have current/upcoming schedule entries, and the final generated output ID is audited after the merge. See `output/postbuild-validation.csv` and `output/postbuild-gaps.csv`. Gabbarit is enabled again as a last-resort Russian/CIS recovery fallback after safer sources.

## v2.0 live-delivery audit

v2.0 adds an automatic end-to-end check after every scheduled build. After GitHub publishes the new EPG and mapping, the workflow requests the live Cloudflare playlist with `?fresh=1` and verifies that the Worker's actual TVG IDs match `uhf-mapping.json` and correspond to post-build-validated XMLTV programmes.

New diagnostics:
- `output/worker-audit.json`
- `output/worker-audit.csv`
- `output/worker-audit-gaps.csv`

The normal player URL remains `/tv`. The `fresh=1` query is for automated diagnostics only.


## v3.0

The builder now supports conservative regional-family matching for international brands, records a confidence score for every mapping, and can persist an explicitly enabled stale-if-error cache for unstable XMLTV sources. Release ZIPs do not contain generated `output/` files.


## v3.3 targeted recovery
- KLI dedicated feed updated to the latest publicly reported endpoint `https://epg.klimedia.pro` and moved before the stale Runigma mirror.
- Added fresh Portugal EPGShare feed with exact aliases for SPORT TV, DAZN PT and Canal 11.
- Added verified exact Greece/Croatia recovery aliases.
- Existing matches remain authoritative; new recovery applies only where source data is present and fresh.

## v4.0 Accuracy

The builder now separates **freshness** from **correctness**. `postbuild-validation`
answers “does this ID have current programmes?”, while `accuracy-audit` answers
“is this mapping plausible for this provider region/feed?”. Obvious country/feed
conflicts are quarantined before `uhf-mapping.json` is published. Real EPG only:
synthetic DITV schedules are disabled.


## v4.1 IMDb metadata enrichment
The builder normalizes IMDb metadata already present in upstream XMLTV and enriches missing fictional movie/series metadata with the v8 resolver. `TMDB_API_KEY` is the only metadata API secret required. TMDb resolves the title and IMDb ID; IMDb rating/vote count are read directly from IMDb and cached by IMDb ID. Reports: `output/metadata-enrichment.json` and `output/metadata-enrichment.csv`.


## TMDb / IMDb resolver
Localized RU/EN fictional titles are resolved through TMDb first, with normalized/transliterated fallbacks and safe movie/series cross-checking. IMDb IDs are obtained from TMDb external IDs. Rating and vote count are then read directly from IMDb and cached separately by IMDb ID; OMDb is only an optional fallback. Identity mappings live in `.cache/metadata/metadata-v70.json`, while volatile IMDb entity data lives in `.cache/metadata/imdb-entities-v70.json`.

## v7.0 metadata resolver

Version 7.0 keeps a single built-in resolver in `src/metadata_enrichment.py` and separates stable title identity from volatile IMDb rating/vote metadata.

Key rules:
- metadata enrichment is limited to fictional movies and fictional series;
- only Russian- and English-language titles are enriched; Ukrainian/Belarusian/other titles are skipped even if an upstream XMLTV source incorrectly labels them as `ru-RU`;
- episode suffixes and multipart mini-series are collapsed to one canonical title, so many episodes share one in-run lookup/cache entry;
- Russian Cyrillic titles also get Latin transliteration variants (for IMDb/TMDb records indexed like `Kupel dyavola`);
- TMDb search can cross-check movie/series type for multipart titles and does not stop at the first TMDb result that lacks an IMDb ID;
- OMDb is queried by IMDb ID for rating; if OMDb returns no rating, the resolver can fall back to IMDb page structured data;
- missing ratings are retried periodically instead of being cached forever;
- v7 uses `.cache/metadata/metadata-v70.json` plus `.cache/metadata/imdb-entities-v70.json`. Successful v6/v5 IMDb-ID mappings are migrated; old negative results are discarded. Obsolete metadata caches are removed only after successful v7 saves. `.cache/epg/` remains important and is never removed by metadata cleanup.

The Actions request ceiling is `METADATA_MAX_REQUESTS` and now counts actual metadata network requests rather than only top-level title lookups.


## Metadata architecture v7.0

`TMDb -> IMDb ID -> direct IMDb rating/votes -> persistent IMDb-ID cache`.

OMDb is not used by v8.0. The runtime metadata path is `canonical RU/EN title → TMDb cascade → TMDb external_ids → IMDb ID → direct IMDb rating/votes`.

Persistent caches:
- `.cache/metadata/metadata-v70.json` — canonical title/type/language -> IMDb/TMDb identity.
- `.cache/metadata/imdb-entities-v70.json` — IMDb ID -> rating, votes, source, checked timestamp.

IMDb entity data refreshes every 30 days; missing rating/votes retry after 7 days. Series episodes share the same canonical identity and IMDb entity entry.


## Metadata engine v8.0

The resolver uses canonical episode collapsing, strict RU/EN language filtering, transliteration, curated aliases, year-aware matching, safe multipart movie/series cross-type fallback, confidence scoring, progressive negative-cache backoff, and separate stable-identity/volatile-rating caches. Curated aliases live in `data/metadata_aliases.json`; they are search hints and never bypass confidence checks.


## Metadata backfill

`Actions → Backfill Movie Metadata` enriches fiction metadata from the already
committed `output/epg.xml.gz`; it does not redownload XMLTV providers.

Inputs:

- `budget`: real TMDb HTTP request budget for the run;
- `dry_run`: report queue size without spending requests.

The durable metadata knowledge base is committed as `data/metadata.sqlite3.gz`.
Git is the persistence layer; `.cache` remains an acceleration layer. Update EPG
and Backfill use the same `concurrency.group`, so they never race on metadata.


### Automatic backfill

The metadata backfill now runs automatically every 6 hours at minute 47. The
normal EPG update runs at minute 17, so the backfill normally follows it. Both
workflows use the same `concurrency.group: epg-metadata`; if one is still running,
the other waits instead of racing.

Scheduled backfill uses a real TMDb HTTP budget of 2500 requests per run and
commits the updated `data/metadata.sqlite3.gz` snapshot automatically. No manual
button presses are required for normal accumulation.


## Single-click Update EPG

`Update EPG` now does the complete cycle in one run:

1. build the current programme from XMLTV sources using metadata already in SQLite;
2. backfill missing/incomplete fiction metadata from that current `epg.xml.gz`;
3. write newly found genres/descriptions/IMDb data back into the same current EPG;
4. save `data/metadata.sqlite3.gz`;
5. commit the final enriched `output/epg.xml.gz`.

No second manual Update EPG run is required.
