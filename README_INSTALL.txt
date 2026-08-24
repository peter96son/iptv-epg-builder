v13.24.2 — test-only fix

This patch fixes the SQLite foreign-key setup in:
tests/test_v1324_year_safe_metadata.py

No production code changes.
No Worker changes.
No EPG mapping changes.

Upload over repo root -> Commit -> rerun Update EPG.
Do NOT redeploy Worker just for this patch.
