# IPTV EPG Builder v11.3.1

Automatic accumulation release.

## Automatic metadata backfill

`Backfill Movie Metadata` now runs automatically every 6 hours:

- Update EPG: minute 17
- Backfill: minute 47

Both workflows share `concurrency.group: epg-metadata`, so they cannot write the
metadata database at the same time. If the EPG update is still running, backfill
waits in the queue.

Scheduled backfill uses 2500 real TMDb HTTP requests per run, reads the already
committed `output/epg.xml.gz`, updates SQLite, writes
`data/metadata.sqlite3.gz`, and commits the durable snapshot.

Manual `workflow_dispatch` remains available, including dry-run and a custom
budget, but normal database growth no longer requires manual launches.
