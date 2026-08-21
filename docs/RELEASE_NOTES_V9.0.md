# IPTV EPG Builder v9.0

- Replaces unreliable IMDb page scraping with IMDb's official Contributor Ratings Dataset.
- Downloads `title.ratings.tsv.gz` at most once every 24 hours and builds a local SQLite index.
- IMDb rating/vote lookups no longer consume the 150-call TMDb budget.
- Keeps TMDb as the primary RU/EN fiction title resolver and IMDb-ID source.
- Stable cache names: `metadata-cache.json`, `imdb-cache.json`, `imdb-ratings.sqlite3`.
- Migrates v8 positive and negative resolver cache entries while stripping obsolete OMDb labels and stale rating data.
- Retains aliases, transliteration, year-aware matching, series canonicalization, cross-type fallback, language filtering, confidence scoring, and progressive negative-cache backoff.
- GitHub Actions workflow remains present and caches the complete `.cache` tree.
- Adds v9 dataset/cache migration tests.

IMDb contributor data is intended for personal/non-commercial use under IMDb's terms.
