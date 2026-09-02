v15.5 — dynamic missing-movie-channel live verifier

This does NOT modify the main EPG build or mapping.

Once per hour it reads output/movie-epg-gaps.csv and automatically probes only
channels that currently have NO_MAPPING / NO_CURRENT_PROGRAMME / NO_NEXT_PROGRAMME
in these groups:
- Кино
- USSR
- Кинозалы
- Кино 4K

For each current gap it:
1. finds the exact provider stream in PLAYLIST_URL;
2. reads ffprobe stream/program metadata;
3. captures three temporary lower-screen frames;
4. OCRs Russian + English text;
5. stores only metadata, OCR text and image hashes in
   output/movie-gap-live-probe.json.

When a channel receives a good EPG and leaves movie-epg-gaps.csv, it is
automatically no longer probed.

No stream URL or video frame is persisted.

v15.5.1 control fix:
- captures all three OCR frames through one live ffmpeg connection;
- frames are sampled at approximately 5/20/35 seconds;
- removes the impossible 45-second seek under a 24-second subprocess timeout;
- worst-case capture time is now bounded at 55 seconds per channel and benefits from 3-way concurrency.

v15.5.2 full approach review:
- consumes every non-OK row produced by movie_epg_audit, including
  ID_NOT_IN_EPG and NO_PROGRAMMES (not only NO_MAPPING/current/next);
- locates the live stream using provider_name, which is the actual M3U name,
  while playlist_name may have been changed by playlist_rules name_overrides;
- raises the per-run safety cap from 60 to 120 channels;
- keeps exact-name/unique-normalized matching to prevent same-brand cross-wiring.

v15.5.3 final integration control:
- checks all current movie gaps by default (no truncation);
- samples one live connection at approximately 4/10/16 seconds;
- uses 4 workers and bounded subprocess timeouts;
- runs at minute 55 to reduce overlap with Update EPG at minute 17;
- redacts URLs found in stream metadata;
- prevents duplicate display-name rows from overwriting each other.
