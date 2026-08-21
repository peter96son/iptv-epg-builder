# IPTV EPG Builder v13.0 — Stage 2

Metadata resolution is now knowledge-first.

Order:
1. linked alias (`aliases.title_id`) -> canonical `titles`;
2. exact canonical `titles` identity;
3. legacy `title_cache` fallback;
4. legacy alias fallback;
5. TMDb only after local miss, or for a known identity that still lacks display metadata.

A known film can therefore populate the EPG with zero TMDb HTTP calls even if its
old `title_cache` row is missing.

Backfill also checks the normalized knowledge layer before queuing work.

Upgrade rule: preserve the existing `data/metadata.sqlite3.gz`. Opening it migrates
the database in place to schema version 3.
