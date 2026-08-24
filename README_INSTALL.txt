v13.23 — ZERO MOVIE GAPS GATE

Upload ALL files over repository root and Commit once.

Then:
Actions -> Update EPG

Do NOT Deploy Worker. Worker 2.2.0 is already correct.

What changed:
- iptv-online-primary now really uses https://iptv.online/epg/epg.xml.gz
- adds Gabbarit current-week rescue + mirror for custom movie channels
- adds full https://epg.one/epg.xml.gz rescue (useful for newly added DITV families)
- hard source pins no longer block a late rescue source after normal sources failed
- verified rescue aliases added for BCU / VeleS / KLI / BOX / Novella / truncated Detective
- strict QA covers ONLY: Кино, USSR, Кинозалы, Кино 4K
- Update EPG WILL NOT PUBLISH if even one channel in those groups has:
  no mapping / no EPG channel / no current programme / no next programme

Reports:
output/movie-epg-audit.json
output/movie-epg-audit.csv
output/movie-epg-gaps.csv

This is deliberate: a green Update EPG now means the four movie categories passed the
real end-to-end programme check. A broken build cannot overwrite the last published EPG.
