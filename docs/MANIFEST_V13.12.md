# v13.12 package manifest

Complete replacement/new files included:

- `src/utils.py` — adds safe XMLTV timestamp shifting.
- `src/xmltv.py` — applies exact per-source/per-source_id shifts before freshness checks and when yielding programmes.
- `src/channel_time_offsets.py` — durable CSV loader with malformed-row protection.
- `data/channel_time_offsets.csv` — CPS USSR (`openbox-tsd` / `cps-ussr`) = +840 minutes.
- `tests/test_channel_time_offsets.py` — +14h, rollover, isolation, malformed CSV regression tests.
- `tests/test_xmltv_channel_time_offsets.py` — end-to-end XMLTVSource regression: CPS USSR shifts; CPS Drama does not.
- `tests/test_core.py` — current v13.11 core regression file retained alongside the modified utils implementation.
- `docs/V13.12_HANDOFF.md` — architecture/handoff notes for the next AI/chat.
- `README_V13.12.txt` — package summary.

Validation: `16 passed` for the included targeted test suite.
