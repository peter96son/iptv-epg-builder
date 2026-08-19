# IPTV EPG Builder v13.0 — Stage 4

Local IMDb layer.

The builder now maintains a local SQLite mirror built from IMDb's official bulk
`title.basics.tsv.gz` and `title.ratings.tsv.gz` datasets.

For a known IMDb ID, per-title IMDb access is now a local SQLite read and costs
zero HTTP requests. The local layer supplies title type, primary/original title,
year/end year, runtime, genres, rating, votes and adult flag.

Matched entities are mirrored into the durable `metadata.sqlite3`, so useful
IMDb data survives eviction of the bulk `.cache/imdb` database.

The old ratings-only local DB remains as a fallback.

Preserve the existing `data/metadata.sqlite3.gz`. Migration to schema v5 is
automatic and non-destructive.
