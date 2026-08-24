# v13.20 manifest

Upload over repository root preserving folders:

- data/source_pins.csv
- data/playlist_rules.json
- data/manual_epg_observations.csv
- cloudflare-worker/worker.js
- cloudflare-worker/worker.test.mjs
- tests/test_v1320_consolidated.py
- docs/V13.20_CONSOLIDATED_FIXES.md

IMPORTANT:
- data/metadata.sqlite3.gz is NOT included and must remain untouched.
- Run Update EPG after commit.
- Because worker.js changed, deploy Cloudflare Worker once.
