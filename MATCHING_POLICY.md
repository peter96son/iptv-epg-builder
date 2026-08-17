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
