v13.22 FINAL MOVIE EPG QA

What this fixes:
1. Restores the actual provider EPG as primary:
   https://iptv.online/epg/epg.xml.gz
   (the repository currently points iptv-online-primary at ip-tv.dev instead).
2. Keeps external sources as fallbacks for missing provider coverage.
3. Adds a strict final audit for Кино / USSR / Кинозалы / Кино 4K.
4. Audit checks the ACTUAL Worker playlist against the generated epg.xml.gz:
   tvg-id, channel existence, current programme, next programme.
5. Writes output/movie-epg-audit.csv and output/movie-epg-gaps.csv.

Attached-current-state audit:
Кино: 180 total, 159 with any EPG, 21 gaps
USSR: 20 total, 17 with any EPG, 3 gaps
Кинозалы: 272 total, 240 with any EPG, 32 gaps
Кино 4K: 82 total, 69 with any EPG, 13 gaps
Total: 554 channels, 69 structural gaps.

IMPORTANT:
Run src/apply_v1322_sources.py once (or use its change manually), then Update EPG.
The movie audit should be wired after Worker refresh/publication; it intentionally fails when a mapped movie channel has no CURRENT programme.
