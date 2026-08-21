# IPTV EPG Builder v11.1

Performance and reliability release.

## Fixed
- Separate unique-title budget from actual TMDb HTTP request budget.
- `_tmdb_lookup_imdb` now receives the HTTP budget; search, external IDs and details consume it.
- Hard metadata wall-clock deadline (default 35 minutes) so enrichment cannot prevent EPG completion.
- SQLite is committed/checkpointed every 25 newly resolved titles.
- Removed artificial `sleep(0.02)` per title.
- TMDb retry sleeps are shorter and respect small `Retry-After` values.
- Stop a lookup after 4 consecutive empty search plans by default.
- Source download timeout/retry caps and a 20-minute source-phase deadline.
- GitHub Actions cache split into restore/save; save runs with `if: always()`.
- XMLTV streaming parser clears the root as top-level records are processed to prevent retained empty elements from growing indefinitely.

## Workflow defaults
- `METADATA_MAX_TITLES=20000`
- `METADATA_MAX_HTTP_REQUESTS=2500`
- `METADATA_DEADLINE_SECONDS=2100`
- `METADATA_TIMEOUT=8`
- `METADATA_CHECKPOINT_EVERY=25`
- `TMDB_EMPTY_PLAN_LIMIT=4`
- `EPG_SOURCE_TIMEOUT_CAP=45`
- `EPG_SOURCE_RETRIES_CAP=2`
- `EPG_SOURCE_DEADLINE_SECONDS=1200`

The GitHub job timeout remains 90 minutes, but internal deadlines are designed to let the build finish well before it.
