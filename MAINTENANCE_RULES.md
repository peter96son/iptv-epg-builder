# Maintenance rules for future edits

1. Update `src/metadata_enrichment.py` directly; do not create sidecar patch modules for normal releases.
2. Before shipping, run `python -m pytest -q` and a Python compile check, then verify `.github/workflows/update.yml` exists inside the final ZIP.
3. Preserve RU/EN-only fictional movie/series enrichment unless the scope is explicitly changed.
4. Never spend one title lookup per episode: canonicalize series titles and keep in-run/persistent caches.
5. Do not trust upstream language tags when title text strongly indicates another language.
6. TMDb is the network title resolver and IMDb-ID source. A TMDb result without IMDb ID is not final until remaining safe variants are tried.
7. Curated aliases live in `data/metadata_aliases.json`; never add guessed translations as aliases.
8. Alias/transliteration/cross-type matches must still pass confidence checks. Ambiguous short titles require stricter thresholds.
9. Negative results use progressive expiry; never permanently blacklist a title because external databases change.
10. IMDb ID is stable identity; rating and vote count are separate volatile metadata.
11. Never scrape IMDb title pages and do not restore OMDb without an explicit architecture decision.
12. IMDb rating/votes come only from the official Contributor Ratings Dataset `title.ratings.tsv.gz`.
13. Build/reuse `.cache/imdb/imdb-ratings.sqlite3`; dataset lookups do not consume the TMDb API budget.
14. Stable caches are `.cache/metadata/metadata-cache.json` and `.cache/metadata/imdb-cache.json`; do not rename them per release without an incompatible schema reason.
15. Preserve `.cache/epg`, `.cache/metadata`, and `.cache/imdb` across GitHub Actions runs.
16. Legacy `tmdb+omdb`, `tmdb+metadata`, and direct-page source labels must never appear in newly generated v9 reports.
17. Generated `output/` is operational state consumed by the Worker; it may be carried in a FULL release but Actions remains authoritative and rebuilds it.
18. IMDb contributor data is for personal/non-commercial use under IMDb's applicable terms. Keep the attribution in README/release documentation.
