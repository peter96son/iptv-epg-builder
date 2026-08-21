# IPTV EPG Builder v11.3

Dedicated metadata backfill release.

## Durable metadata

The SQLite knowledge base is snapshotted as `data/metadata.sqlite3.gz` and
committed to git. Git is the durable source of truth; GitHub Actions cache is
still used as a speed layer for other cached artifacts.

Every Update EPG run restores the git snapshot before building and saves a new
snapshot afterward.

## Backfill workflow

New workflow: `Backfill Movie Metadata`.

It reads the already committed `output/epg.xml.gz` and `output/mapping.csv`.
It does not redownload the XMLTV source fleet.

The queue contains all fiction candidates. Movie groups (`Кино`, `Кино 4K`,
`Кинозалы`, `Кинозалы UA`) are processed first, then explicit films, then
series, then other fiction.

Existing negative-cache TTL/backoff is respected by the normal enrichment
engine, so repeated backfill runs do not waste budget on fresh known misses.

Workflow inputs:
- `budget` — actual TMDb HTTP request budget;
- `dry_run` — queue/report only, zero TMDb requests.

Both Update EPG and Backfill share `concurrency.group: epg-metadata`, preventing
lost updates from simultaneous cache/database writers.

## Report

`output/metadata-backfill.json` includes:
- `total_unique`
- `with_overview`
- `with_genres`
- `remaining`
- `http_spent`
- before/after queue state
- stop reason and remaining budget.
