# v8.0

- Removed OMDb from the runtime metadata architecture and GitHub Actions.
- TMDb is the sole title resolver; IMDb ID comes from TMDb external IDs.
- IMDb rating and vote count are read directly from IMDb and cached by IMDb ID.
- Added curated `data/metadata_aliases.json`; aliases never bypass confidence validation.
- Added confidence scoring for every matched title and stricter thresholds for short/ambiguous titles.
- Added progressive negative-cache backoff (2/7/30 days) instead of repeatedly spending requests on stable misses.
- Preserved RU/EN-only fiction filtering, Ukrainian rejection, canonical series collapsing, transliteration, year-aware and multipart cross-type fallback.
- Added retry/backoff for JSON HTTP calls and direct IMDb page retrieval.
- Migrates positive v7/v6/v5 title mappings; stale negative mappings are discarded.
- New caches: `metadata-v80.json` and `imdb-entities-v80.json`.
- GitHub Actions workflow is preserved and now runs the test suite before building.
