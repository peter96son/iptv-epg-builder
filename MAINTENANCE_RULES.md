# Maintenance rules for future edits

1. Do not create sidecar metadata patch modules for normal releases. Update `src/metadata_enrichment.py` directly.
2. Before shipping, run `python -m pytest -q` and `python -m py_compile src/metadata_enrichment.py`.
3. Preserve RU/EN-only fiction enrichment unless the policy is explicitly changed.
4. Do not spend one API lookup per episode: canonicalize series titles and use in-run memo/cache keys.
5. Do not trust provider language tags when title text strongly indicates another language.
6. Do not cache `not_found` forever. Positive IMDb-ID matches may be long-lived; negatives must expire.
7. Do not delete `.cache/epg`; it is stale-if-error protection for unstable XMLTV sources.
8. Generated `output/` is operational state consumed by the Worker. Code releases may preserve it, but it is rebuilt by Actions.
9. A TMDb result without IMDb ID is not a final failure until remaining safe resolver variants have been tried.
10. IMDb rating is separate from IMDb ID. A valid ID with missing rating remains an enriched record and may be refreshed later.


## v7 metadata rules

11. TMDb is the primary title resolver. IMDb ID is the stable identity key.
12. IMDb rating and vote count are volatile entity metadata and live in `imdb-entities-v70.json`, keyed by IMDb ID.
13. Query IMDb directly only for a new/stale IMDb ID; do not request rating per episode or per channel occurrence.
14. Refresh IMDb entity metadata after 30 days. If both rating and votes are missing, retry after 7 days.
15. OMDb is optional fallback only when direct IMDb metadata retrieval yields no rating/votes. Never require OMDb for title resolution.
16. Do not add Kinopoisk as a rating source unless the policy is explicitly changed.
