V14.6 FINAL CUMULATIVE

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
