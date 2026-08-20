IPTV EPG Builder v13.10 — Stage 7 hotfix

Fix:
- `people.imdb_id` is UNIQUE in SQLite.
- New TMDb people usually do not have a person IMDb ID at this stage.
- v13.9 inserted an empty string, so the second person failed UNIQUE.
- v13.10 stores NULL instead. SQLite permits multiple NULL values in a UNIQUE column.

Included paths:
src/stage7_credits.py
tests/test_stage7_credits.py
tests/test_verified_schedule_fixes.py
docs/PROJECT_PLAN_STAGE7.md

Copy folders into repository root preserving paths, then run:
python -m pytest -q
