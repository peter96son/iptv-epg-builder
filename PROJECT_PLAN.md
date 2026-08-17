# Project plan

This is the persistent development plan. Do not rely on chat history for these decisions.

## Primary user outcome

Provide a continuously updating pair for UHF:

1. `output/playlist-uhf.m3u`
2. `output/epg.xml.gz`

The user configures UHF once; GitHub Actions keeps both updated.

## Production flow

Private IPTV Online M3U in GitHub Secret `PLAYLIST_URL`
→ GitHub Actions every 6 hours
→ fetch current provider playlist
→ fetch primary and fallback EPG sources
→ validate fresh `<programme>` data
→ build merged XMLTV
→ build UHF companion M3U
→ commit outputs.

## UHF companion playlist rules

`playlist-uhf.m3u` must:
- preserve every stream URL exactly;
- preserve channel order;
- preserve display names;
- preserve `tvg-logo`;
- preserve `tvg-name`;
- preserve provider `#EXTGRP` categories exactly;
- replace/add only the EPG URL and verified `tvg-id`;
- point `url-tvg` to `output/epg.xml.gz`;
- use the same final IDs as XMLTV;
- never expose the private original playlist URL.

## Development priorities

1. Stable UHF playlist + EPG pair.
2. Correct broken/conflicting `tvg-id`.
3. Increase EPG coverage; movie groups first.
4. Audit correctness of programme mappings, not only presence.
5. Dashboard/history.

## EPG correctness audit

The primary IPTV Online EPG is a baseline, not unquestionable ground truth.

Future quality states:
- verified
- likely
- conflict
- unknown

Special checks:
- regional variants;
- +2/+4/+7 and other time-shift channels;
- HD/SD variants;
- duplicated provider IDs;
- ambiguous generic names.

## Language scope

High priority:
- Russian
- Ukrainian
- Belarusian
- English
- German
- Dutch

## Movie priority

First research:
- Кино
- Кино 4K
- Кинозалы
- Кинозалы UA

Handle channel families systematically: Magic, KLI, Velilla, BCU, CPS, NEXT, KBC, CineMan, MM/MiniMax, Fresh, BOX, Clarity, Play-X and newly discovered families.

## Safety

- Fresh `<programme>` required for coverage.
- Never guess ambiguous mappings.
- `no_epg_*` is not a valid ID.
- Malformed external timestamp must not crash the build.
- Preserve last known good output if programme volume collapses.


## v1.3 reliability requirements

Every successful build must now keep:
- `output/playlist-snapshot.json`
- `output/playlist-changes.json`
- `output/history.json`
- `output/dashboard.md`
- `output/dashboard.html`

Safety:
- Reject a playlist that suddenly loses more than 15% of channels relative to the last successful snapshot.
- Do not overwrite a known-good published playlist/EPG when a safety stop triggers.
- Track additions, removals, renames, category changes and stream URL changes.
- New channels automatically become part of the next build; if no EPG is found they remain in `unmatched.csv`.
- Track cumulative source contribution so weak/dead sources can be removed later.


## v1.4 private delivery architecture

The public GitHub repository MUST NOT contain an M3U with actual provider stream URLs.

GitHub publishes only:
- `output/epg.xml.gz`
- `output/uhf-mapping.json`
- reports and diagnostics

Cloudflare Worker delivers the private playlist:
- `PLAYLIST_URL` is an encrypted Worker secret.
- `ACCESS_TOKEN` is an encrypted Worker secret and acts as the bearer path.
- UHF uses `/playlist/<ACCESS_TOKEN>`.
- Worker fetches the latest provider M3U on demand.
- Worker preserves stream URLs, order, names, logos and categories.
- Worker rewrites only the EPG URL and verified TVG IDs.
- Worker never writes the generated M3U to GitHub.
- If an old public `output/playlist-uhf.m3u` exists, the next successful GitHub build must delete it.
