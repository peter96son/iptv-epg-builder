# v13.9 — Stage 7

Stage 7 adds normalized directors and actors using the existing Stage-1 `people` and `credits` tables.

Repository paths:
- `src/stage7_credits.py`
- `tests/test_stage7_credits.py`
- `tests/test_verified_schedule_fixes.py`

Rules:
- credits are database-first;
- TMDb credits are fetched only when missing;
- director and top-billed actors are stored in `people`/`credits`;
- XMLTV uses standard `<credits>`;
- actor/director text is not appended to `<desc>`;
- verified РуКино mapping remains `Xklirussian`.

Version: 13.9-stage7.
