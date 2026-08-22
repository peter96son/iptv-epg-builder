Copy to repository root preserving folders:

src/channel_time_offsets.py
data/channel_time_offsets.csv
data/playlist_rules.json
tests/test_channel_time_offsets.py
cloudflare-worker/worker.js
cloudflare-worker/worker.test.mjs
docs/V13.15_HANDOFF.md

After Worker deployment request `/tv?fresh=1` once to bypass an old cached playlist.
