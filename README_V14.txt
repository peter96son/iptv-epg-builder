V14.7 FINAL CUMULATIVE

Upload over repository root with replacement.

Locked cumulative behavior:
- preserves all previous category corrections;
- Fresh TV Armenia -> Музыкальные;
- Viasat True Crime CEE -> Познавательные;
- KBC Animals and MM Микромир/Макромир/Мегамир -> Познавательные;
- preserves previous BCU/Fresh/Magic/VeleS/Insomnia source pins;
- all agreed V14 channel moves -> Сериалы;
- any channel name containing сериал/serial is automatically put in Сериалы;
- Cine+, Твоє/Твое Кино and PROKINO are removed;
- Worker rewrites BOTH EXTINF group-title and #EXTGRP;
- Наш Кинопоказ HD remains distinct from Наш Кинопоказ;
- Наше любимое кино uses the Russian feed, not UA;
- KinoSweet uses Russian-language EPG priority;
- MM USSR Сказки HD has an explicit EPG mapping;
- 4ever uses exact channel IDs with source fallback only when the preferred
  source has no usable current programme;
- Воен ТВ HD candidates are non-forcing;
- no broad fuzzy channel matching;
- HD/FHD/UHD/4K are not blindly collapsed into another channel identity;
- х/ф, x/ф, т/ф and м/ф are removed BEFORE TMDb/IMDb lookup;
- т/с, сериал, мультсериал, season/episode and SxxExx forms are recognized;
- Три кота (Картинная галерея) -> Три кота;
- Простоквашино (Неудобные соседи) -> Простоквашино;
- metadata backfill imports the same cumulative title-normalization policy;
- obsolete src/v14_policy_patch.py is not required.

After upload:
1. Commit.
2. Run Update EPG.
3. Deploy Cloudflare Worker.
4. Open /tv?fresh=1 once.

V14.7: fixes CI year normalization regressions: parenthesized production year is removed, title-number 2049 is preserved.

V14.9 delivery safety hotfix:
- Cine+, Твоє/Твое Кино, PROKINO and 1+1 Кіно are now hard-blocked inside Worker code.
- This block works even when playlist_rules.json cannot be loaded.
- Worker cache key bumped to v14.9.

V14.10 UniPlayer compatibility:
- matched channels always receive exact output tvg-id and deterministic tvg-name;
- mapping lookup tolerates case/whitespace differences;
- EPG URL is versioned with uhf-mapping generated_at so UniPlayer refreshes after each EPG build;
- UHF and UniPlayer use the same verified mapping contract.

V14.11 Ukrainian-only exclusions + MM USSR Adventures freshness:
- hard-excludes Star Cinema/HD, M1 HD, M2 HD, MusicBox UA HD, UA.Music HD,
  Серіал Україна 1/2, FilmUA Drama, Про Київ and EWTN Украина/Україна;
- Ukrainian sports channels are intentionally kept;
- MM USSR Приключения HD is hard-pinned to the already configured
  gabbarit-primary source_id ussr-prikluchenija-mm so the short provider EPG
  cannot consume the channel before the longer fresh MM schedule is considered;
- Worker version/cache key bumped to v14.11.


v14.12 — EPG anti-stale horizon guard
------------------------------------
- XMLTV channel matches now require at least 12 hours of future schedule by default (EPG_MIN_FUTURE_HOURS).
- A short-horizon source is deferred, allowing later configured sources to win automatically instead of first-source-wins causing stale EPG.
- Update EPG runs every 6 hours, so 12 hours provides two normal build intervals of safety margin.
- Final EPG horizon QA refuses publication if any published UHF mapping has less than 6 hours of programme horizon.
- Reports: output/epg-horizon-audit.json and output/epg-horizon-audit.csv.
- MM USSR Приключения HD keeps the v14.11 hard pin to gabbarit-primary / ussr-prikluchenija-mm.
- Existing Ukrainian hard-exclude policy and all v14.10/v14.11 fixes are preserved.
