v15.18 evidence-first correction

1. Removes the v15.17 runtime import that hard-pinned BCU VHS HD / BOX Oscar HD
   to an unproven Torrent-TV schedule.
2. Adds timestamped live observations as evidence:
   BCU VHS HD -> Адвокат дьявола
   BOX Oscar HD -> Аватар
   BCU Criminal HDR -> Васаби
3. Adds an evidence-aware candidate layer. A donor wins only when its programme
   at the observation timestamp matches the observed title. The winner is stored
   in data/source_evidence_state.json and reused while its schedule stays usable.
   Later contradictory evidence can replace it.
4. Scans same-family BCU/BOX candidates instead of assuming the playlist name
   equals the actual schedule identity.
5. Keeps epg-metadata concurrency and safe-publish.
6. Adds conservative GitHub Actions housekeeping: keep the newest 20 completed
   runs per workflow; cleanup never fails the EPG build and does not touch Git
   commits, EPG files, caches or metadata.
