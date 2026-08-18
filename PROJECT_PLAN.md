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

## v1.5 unmatched-family diagnostics

Version 1.5 changes the development workflow from chasing unmatched channels one by one to researching families systematically.

Generated diagnostics now include:
- `output/unmatched-families.json`
- `output/unmatched-families.csv`
- `output/unmatched-families.md`

Known families are grouped explicitly, including DITV, VeleS, Magic, KLI, Play-X, BCU, Joker, Clarity, CPS, NEXT, CineMan, MiniMax/MM, Fresh, BOX, Velilla and KBC. Newly discovered prefixes are grouped into diagnostic `Other: ...` buckets.

The family classifier is diagnostic only. It MUST NOT create live EPG mappings. New mappings still require a real XMLTV source, fresh `<programme>` data and a verified identity.

### Worker delivery in v1.5

The current Cloudflare Worker no longer uses `ACCESS_TOKEN` or `/playlist/<ACCESS_TOKEN>`.

Production routes:
- `/tv` — IPTV-player playlist, `inline` response;
- `/download` — same rewritten playlist as a downloadable `playlist.m3u`;
- `/epg` — redirect to the generated EPG;
- `/health` — upstream health check.

Worker `PLAYLIST_URL` stays private in Cloudflare. The public GitHub repository contains no provider stream URLs.

For unmatched channels in protected movie groups (`Кино`, `Кинозалы`, `Кино 4K`, `Кинозалы UA`), Worker removes `tvg-id` and `tvg-name` so players cannot attach unrelated EPG data. It also removes dummy `no_epg_*` IDs from unmatched channels globally.

Core rule: **No EPG is better than a false EPG match.**

## v1.6 region-aware matching

Channel display names are not globally unique. Matching must use provider group/country context.

- Infer region from IPTV.online provider group where possible.
- Regional-sensitive brands (Discovery, Eurosport, Viasat, HBO, Nickelodeon, Disney, MTV, BBC/ITV/RAI/RTL, beIN, etc.) may only auto-match by name against a source with a compatible `regions` scope.
- A global/unknown-region XMLTV source must not win a name-only match for these brands.
- Manual aliases may carry `provider_group` and/or `region` constraints.
- Preserve `No EPG` rather than assigning a plausible but wrong regional schedule.
- See `MATCHING_POLICY.md`; it is persistent project instruction.


## v1.7 verified mainstream regional aliases

Version 1.7 turns region-aware policy into production mappings.

Rules:
- Add only aliases verified against a country-specific source catalog.
- Alias rows must carry `provider_group`, normalized `region`, explicit `source`, and exact `source_id`.
- Do not use a same-brand schedule from another country to fill a gap.
- Country-specific absence is meaningful diagnostic evidence; preserve No EPG until another verified local source is found.
- Current verified batches cover selected Italy, UK, Romania and Bulgaria mainstream channels.
- `Discovery Science HD RO` is deliberately not mapped from UK or generic Discovery Science data.

Next research queue after v1.7 live results: BE/NL disambiguation, Israel, Germany/Austria edge cases, then safe sports services. DITV/Play-X/Clarity remain protected from speculative fuzzy matching.

## v1.8 Russian/CIS recovery

- Add EPG.ONE Russian-language XMLTV (`https://epg.one/ru2.xml.gz`) as a fallback source.
- Scan Russian/CIS unmatched channels across the whole playlist, not only the `Россия` group.
- Publish `unmatched-russian-cis.json`, `.csv`, and `.md` on every build.
- Keep regional-sensitive brands and time-shift variants fail-closed.
- Keep virtual/FAST families out of generic automatic matching.

## v1.9 final-guide validation and recovery

v1.9 changes the definition of a covered channel.

A mapping alone is not coverage. A channel is publishable to `uhf-mapping.json` only when its final `output_tvg_id` has at least one programme in the generated XMLTV and at least one programme that is current or starts within the near-future usability window.

New diagnostics:
- `output/postbuild-validation.json`
- `output/postbuild-validation.csv`
- `output/postbuild-gaps.csv`

A channel in `postbuild-gaps.csv` must not be published as successfully covered. This rule exists specifically to catch cases where an IPTV player shows `No programme` even though `mapping.csv` contained a TVG ID.

The source eligibility window is stricter than the old calendar-date freshness test. Old entries from yesterday/two days ago must not make a channel look covered. The builder should prefer another fallback source that has current/upcoming data.

Gabbarit is re-enabled in v1.9 only as the LAST recovery fallback and only for Russian/CIS plus thematic groups. It must never outrank dedicated/country-scoped sources. Regional-sensitive brands remain protected by region rules.

## v2.0 end-to-end delivery audit

The production definition of success is no longer "builder produced a mapping".
A channel is considered delivered correctly only when all three layers agree:

1. `output/uhf-mapping.json` contains the expected final TVG ID;
2. the live Cloudflare `/tv?fresh=1` response actually contains that same TVG ID for the channel;
3. the final `output/epg.xml.gz` has a post-build-validated programme for that ID.

Every GitHub Action run must publish:
- `output/worker-audit.json`
- `output/worker-audit.csv`
- `output/worker-audit-gaps.csv`

The workflow commits normal EPG output first, then audits the live Worker against the just-published mapping and commits the audit separately.

`?fresh=1` is diagnostic only. It bypasses the Worker's 15-minute playlist cache and must not replace the normal `/tv` URL configured in IPTV players.

A clean post-build audit plus a clean Worker audit means the remaining "No programme" problem is likely player-side EPG cache/binding rather than builder/Worker delivery.

v2.0 also adds `teleguide-ru` as another Russian/CIS recovery source. It is a fallback only; it does not change the rule that regional-sensitive brands must not be matched across countries by name.

## v3.0 architecture checkpoint

- Add conservative regional family matching for international channel brands.
- Add per-mapping confidence scores and confidence distribution diagnostics.
- Add persisted stale-if-error XMLTV cache for explicitly configured unstable sources (initially Teleguide).
- Keep Worker delivery audit and post-build fresh-programme validation mandatory.
- Release archives exclude `output/` to avoid conflicts with GitHub Actions generated files.

## v3.2 — DITV fallback

DITV channels are handled by a last-resort local XMLTV fallback only after all real EPG sources and verified family matching have failed. The fallback must never invent movie or episode titles. It emits generic on-air blocks and is clearly marked as synthetic in status/source diagnostics. Any future verified DITV XMLTV source automatically takes priority because the fallback only sees still-unmatched DITV channels.


## v3.3 targeted recovery
- KLI dedicated feed updated to the latest publicly reported endpoint `https://epg.klimedia.pro` and moved before the stale Runigma mirror.
- Added fresh Portugal EPGShare feed with exact aliases for SPORT TV, DAZN PT and Canal 11.
- Added verified exact Greece/Croatia recovery aliases.
- Existing matches remain authoritative; new recovery applies only where source data is present and fresh.

## v4.0 Accuracy Gate

Coverage is no longer the primary KPI. A mapping must be both fresh and plausible.
The builder quarantines explicit country/feed conflicts before publishing `uhf-mapping.json`.
`output/accuracy-audit.csv` records every mapping as verified, probable, unverified, or wrong.
`output/accuracy-quarantine.csv` contains mappings removed from player delivery.
Synthetic DITV schedules are disabled: no real programme source means no EPG.
Manual research can be recorded in `data/accuracy_overrides.csv` with an evidence URL.
