# Verified regional recovery — v1.7

Date: 2026-08-17

Purpose: recover mainstream channels only when the provider country/group and the XMLTV country feed agree.

## Added verified aliases

- Italy / `epgshare-IT`: 8 RAI services.
- UK / `epgshare-UK`: ITV 1–4 HD and 3 Sky Cinema services.
- Romania / `epgshare-RO`: ProTV family, CBS Reality RO, Prima TV, Pro Cinema, Realitatea Plus, Romania TV, TVR2/3/Iași, FilmBox Premium, ZU TV.
- Bulgaria / `epgshare-BG`: Diema, Diema Family, Nova, Nova Sport, BNT1/2, Planeta Folk, SKAT.

Every alias is constrained by `provider_group`, normalized `region`, explicit `source`, and exact `source_id`. Runtime fresh-programme gating still decides whether it contributes to production.

## Deliberately NOT mapped

- `Discovery Science HD RO` — provider group `Румыния` / region `RO`. The checked EPGShare Romania catalog does not list Discovery Science. Do not substitute the UK `Disc.Science.uk` schedule or another regional version.

## Next research queue

1. BE/NL: first disambiguate Belgium vs Netherlands within provider group `BE & NL`.
2. Israel: add a country-scoped source and verify mainstream channels.
3. Germany/Austria: resolve channels where the provider group `Германия` mixes DE and AT services.
4. Sports: only named linear channels with clear regional identity; leave event/virtual feeds such as Football Live/VIP/Pimple/FintGa alone unless a dedicated schedule exists.
5. DITV / Play-X / Clarity / VeleS: no speculative fuzzy matching.
