# v10.0.1

Hotfix for the v10.0 test regressions.

- Restores `resolver=tmdb` on legacy cache rows that are queued for v10 revalidation, preserving v8/v9 cache migration compatibility.
- Checks significant sequel/part numbers from the raw provider title before transliteration confidence checks, so `Лютый 2. 1 с.` is rejected as `translit_lost_significant_number` when the query collapses to `Lyutyy`.
- Keeps v10.0 genre/overview enrichment and the 20,000 metadata-request workflow ceiling unchanged.

Targeted regression tests: 2 passed. Python compile check: passed.
