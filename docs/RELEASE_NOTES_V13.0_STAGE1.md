# IPTV EPG Builder v13.0 — Stage 1

Stage 1 creates the normalized long-lived metadata knowledge layer.

New normalized tables:
- `titles`
- `metadata`
- `people`
- `credits`
- `statistics`

The existing `aliases` table gains `title_id`, linking aliases to canonical works.

Compatibility:
- `title_cache` and `imdb_entities` remain live.
- Existing v12 code keeps working.
- Successful writes are mirrored into the normalized v13 tables.
- Existing SQLite databases migrate automatically and idempotently when opened.
- `title_cache.knowledge_title_id` links schedule-resolution rows to canonical titles.

Important upgrade rule:
Do **not** replace or delete the existing `data/metadata.sqlite3.gz`.
It contains the accumulated knowledge base. Update the code files around it.

The new `python -m src.metadata_knowledge` command prints schema/count diagnostics.
