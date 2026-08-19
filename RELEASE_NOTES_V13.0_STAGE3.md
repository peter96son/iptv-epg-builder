# IPTV EPG Builder v13.0 — Stage 3

Conflict-safe intelligent aliases.

High-confidence matches now generate safe formatting aliases for provider prefixes,
quotes, ё/е, HD/FHD/UHD/4K/1080p/2160p suffixes, trailing years and dash spacing.
Sequel numbers are preserved.

Aliases never silently redirect to another canonical work. Conflicts are written to
`alias_conflicts`; repeated same-identity observations increment `evidence_count`.

Keep the existing `data/metadata.sqlite3.gz`; migration to schema v4 is automatic.
