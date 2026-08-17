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
Store `PLAYLIST_URL` and `ACCESS_TOKEN` as Cloudflare Worker secrets.

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
