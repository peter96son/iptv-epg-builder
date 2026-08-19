# IPTV EPG Builder 6.0

This is a full-project release based on the supplied archive.

Main changes:
- Builder status version raised to 6.0.
- Metadata resolver consolidated into the normal `src/metadata_enrichment.py`; no `metadata_enrichment_v51.py` or special `run.py` shim is required.
- RU/EN fiction-only language gate strengthened.
- Russian transliteration fallback added.
- Multipart `х/ф ... 1 с.` entries are treated as series for metadata resolution and share canonical lookup keys.
- Series episode/subtitle text is collapsed before cache/API lookup.
- Years embedded in series schedule titles are no longer treated as production years.
- TMDb `no_imdb_id` no longer stops the search cascade prematurely.
- OMDb missing-rating fallback to IMDb structured page data added.
- Empty IMDb ratings are eligible for periodic refresh.
- Metadata cache schema moved to `metadata-v60.json`; only successful old results are migrated. Obsolete metadata caches are cleaned after a successful save; XMLTV source fallback cache remains intact.
- Actual network request budget is tracked.
- Added v6 regression tests including a 120-episode single-lookup test.
- Removed macOS archive junk (`__MACOSX`, `.DS_Store`) from the release package.

Validation: 57 tests pass.
