IPTV EPG Builder v13.25.2
Safe upgrade for current v13.25.

Included:
- series recognition: т/с, сериал, мультсериал, episode/season suffixes;
- explicit handling for "Три кота (Картинная галерея)" and
  "Простоквашино (Неудобные соседи)";
- HD/FHD/UHD/4K delivery suffix normalization for channel-family matching,
  including MM USSR Сказки HD and 4ever/DITV variants;
- no broad fuzzy matching.

Apply to current repository:
1) overwrite src/channel_family.py with the included file;
2) copy apply_v13_25_2.py to repository root;
3) run: python apply_v13_25_2.py
4) run the normal workflow.
