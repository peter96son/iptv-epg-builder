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
