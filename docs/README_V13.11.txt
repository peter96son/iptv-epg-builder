IPTV EPG Builder v13.11 — full project

Full replacement package. Preserve folder structure.

Fixes:
- source_pins.csv corrected to the declared 9-column schema.
- CSV loader hardened: malformed surplus columns can no longer crash run.py.
- Stage 7 director/actor module and tests included.
- verified schedule fixes retained, including РуКино HD -> Xklirussian.
- builder/metadata/Stage7 version markers synchronized to 13.11.

Important persistent metadata snapshot:
- data/metadata.sqlite3.gz

This ZIP intentionally does not contain .git or runtime .cache.
