# v9.1 quality patch

This patch sits on top of v9.0 and keeps the 2000-request TMDb budget.

Changes:
- rejects unsafe transliteration identities (e.g. Kler -> Clergy);
- preserves sequel/part numbers during transliteration (e.g. Лютый 2);
- prevents generic dotted-title root collapse (e.g. Кремень. Освобождение -> Кремень);
- retains the known Наш спецназ.<region> root behavior;
- forces legacy found-cache rows with blank confidence through revalidation;
- marks runtime metadata version as 9.1 / cache schema 10.

Install:
1. Add `src/metadata_quality_patch.py`.
2. Replace `run.py` with the included version.
3. Add `tests/test_metadata_quality_v91.py`.
4. Keep `.github/workflows/update.yml` with `METADATA_MAX_REQUESTS: "2000"`.
5. Run `Update EPG`.
