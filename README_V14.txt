IPTV EPG Builder — V14
======================

Upload this ZIP over the current repository root.

V14 includes the agreed changes:
- Series group overrides: Лавстори HD, Хит HD, Наше Мужское HD,
  viju TV1000 Romantica, Amedia Hit, Red/.Red HD, SciFi/.Sci-Fi,
  НТВ Хит, Сериал/Серіал Украина 1/2, Lost HD, Новелла ТВ,
  Дорама HD, Kino 1, Русский Бестселлер, Русский Детектив.
- Remove all Cine+ family channels from the generated private playlist.
- Remove Твоє Кіно / Твое Кино Ukrainian family.
- Remove PROKINO.
- Keep Сериал Украина 1/2 and move them to Сериалы (not excluded).
- Exact EPG pins for 4ever Cinema/Drama/Theater/Music.
- MM USSR Сказки HD -> minimax-ussr-skazki.
- Наш Кинопоказ HD -> its dedicated HD EPG; never collapse to Наш Кинопоказ.
- Наше любимое кино -> Russian feed, never UA.
- KinoSweet -> Openbox/TSD schedule priority to avoid Ukrainian EPG language.
- Voen TV HD gets several safe ID candidates without hard-locking a wrong feed.
- HD/FHD/UHD/4K are no longer stripped by generic family matching.
- Safer series title recognition:
  т/с, сериал, мультсериал, season/episode suffixes, SxxExx,
  "Мамочки. 13 с", plus verified parenthetical forms:
  "Три кота (Картинная галерея)" and
  "Простоквашино (Неудобные соседи)".
- Backfill imports V14 policy and remains lean.

After upload:
1. Commit files.
2. Run Update EPG.
3. Deploy Worker (worker.js changed).
4. Refresh /tv?fresh=1 once.
5. Backfill Movie Metadata can then run normally/nightly.

V14 deliberately avoids broad fuzzy channel remapping.
