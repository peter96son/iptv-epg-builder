# IPTV EPG Builder v11.4

Coverage-focused release.

- Backfill processes one synthetic programme per unique metadata key instead of
  scanning hundreds of thousands of repeated broadcasts through enrichment.
- Partial known identities are refreshed before unknown titles.
- Fresh negative-cache entries are skipped.
- Movie groups remain first among unknown work.
- Scheduled backfill default rises from 2500 to 5000 real TMDb HTTP requests.
- Conservative title variants remove season/part schedule noise without removing
  sequel numbers.
- Backfill enables one final TMDb multi-search fallback for provider movie/series
  type mistakes.
- Durable `data/metadata.sqlite3.gz`, automatic scheduling, and shared concurrency
  remain unchanged.
