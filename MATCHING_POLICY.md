# EPG matching policy — v1.6+

This file is a persistent instruction for future work. Do not rely on chat history for these rules.

## Core rule

Correctness is more important than coverage. `No EPG` is better than a wrong schedule.

## Region-aware identity

A channel name is NOT globally unique. The effective matching identity is:

`normalized channel name + provider group/region + optional language + provider tvg-id`

Examples such as Discovery Science, Eurosport, HBO, Nickelodeon, Viasat, MTV, BBC/ITV/RAI/RTL and other international brands can have different schedules by country.

For regional-sensitive brands, automatic name matching is allowed only when the XMLTV source declares a compatible `regions` scope. A global/unknown-region source must not auto-match those brands by display name.

Provider group is the primary region signal. Unknown groups stay unknown until explicitly reviewed.

## Match order

1. verified manual alias, optionally constrained by provider group/region;
2. exact provider tvg-id present in the source;
3. exact normalized name;
4. for regional-sensitive brands, exact normalized name + compatible region is mandatory;
5. no aggressive fuzzy matching for virtual/FAST/cinema families;
6. otherwise unmatched.

## Protected/virtual families

Do not aggressively fuzzy-match DITV, VeleS, Magic, KLI, Play-X, BCU, Joker, Clarity4K, CPS, NEXT, CineMan, MiniMax/MM, Fresh, BOX, Velilla, KBC or newly discovered similar families.

## Source rules

Country-specific XMLTV feeds must declare `regions` in `data/sources.json`. Source `enabled: false` must be respected by the builder.

## Output diagnostics

`mapping.csv` must show the actual method (`alias`, `id`, `name`, `name-region`).
`unmatched.csv` and family reports must include provider group and inferred region.

## Safety

Never publish the provider M3U or stream URLs in GitHub. Cloudflare Worker remains the private playlist delivery layer.


## Verified alias provenance (v1.7)

Production aliases for regional-sensitive or renamed channels must identify the exact country-scoped source. A row without an explicit source and region should not be added for a global brand. When a country's catalog does not contain the service, do not substitute another country's same-brand schedule.

## Russian/CIS cross-group rule (v1.8)

Language/topic grouping is not country identity. A Russian-language channel may appear in `Кино`, `Музыкальные`, `Познавательные`, `Детские`, `Спорт`, or another topical provider group. Recovery research therefore scans all such groups, but region-sensitive channel brands still require compatible regional evidence. Time-shift variants are separate schedules by default.

## v1.9 final validation

Matching and coverage are separate stages.

1. Matcher proposes a source channel.
2. Source must have current/upcoming programme data.
3. Builder emits programmes under the final output TVG ID.
4. Post-build validation confirms that the final ID really has usable programmes.
5. Only then may the channel enter `uhf-mapping.json`.

This prevents a structurally valid TVG ID from producing `No programme` in UniPlayer/UHF.

## v2.0 delivery invariant

Matching is not complete until delivery is verified. For every published mapping:

`playlist channel name -> output_tvg_id -> Worker /tv actual tvg-id -> final XMLTV programme`

must form one consistent chain. Any mismatch is reported in `worker-audit-gaps.csv` and must not be hidden by coverage statistics.

The Worker diagnostic request uses `/tv?fresh=1` to bypass only the Cloudflare playlist cache. Normal player traffic continues to use `/tv` with the 15-minute cache.

## v3.0 regional family matching

- International brands with regional schedules may be matched through a canonical family name only inside a source whose declared region is compatible with the provider group.
- Country suffixes/prefixes such as `RO`, `PL`, `UK`, `Italia`, `Polska` may be removed only at the edge of a regional-sensitive brand name.
- This is not fuzzy matching. A unique exact family name must exist in the compatible country feed.
- Confidence is recorded for every mapping: alias 100, exact ID 99, exact regional name 96, regional family 92, ordinary exact normalized name 90.
- Lower-confidence methods must never override a higher-confidence researched alias.
- `Discovery Science HD RO` may resolve to `Discovery Science` in an RO feed; it must not resolve to the same display name in a GB/NL/PL feed.

## DITV synthetic fallback

DITV remains protected from fuzzy matching to unrelated channels. If no verified DITV schedule exists, the builder may emit a generic synthetic on-air block under a dedicated stable DITV XMLTV ID. Synthetic DITV mappings use low confidence and source `ditv-local-fallback`; they must not be described as exact programme data.


## v3.3 targeted recovery
- KLI dedicated feed updated to the latest publicly reported endpoint `https://epg.klimedia.pro` and moved before the stale Runigma mirror.
- Added fresh Portugal EPGShare feed with exact aliases for SPORT TV, DAZN PT and Canal 11.
- Added verified exact Greece/Croatia recovery aliases.
- Existing matches remain authoritative; new recovery applies only where source data is present and fresh.
