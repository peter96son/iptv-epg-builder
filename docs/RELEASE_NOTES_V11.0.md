# IPTV EPG Builder v11.0

## Overview

v11.0 replaces the old metadata-cache approach with a persistent SQLite metadata engine and restructures film/series enrichment around local reuse first, external lookup second.

The goal is simple: once a title is identified correctly, the builder should remember it and avoid repeating the same work on every EPG run.

## Main changes

### SQLite metadata cache

New file:

`src/metadata_db.py`

Persistent database:

`.cache/metadata.sqlite3`

The database stores:

- title lookup results;
- IMDb entities;
- learned aliases;
- overview/description;
- genres;
- IMDb rating and vote count;
- optional Kinopoisk fields;
- TMDb/IMDb identity links;
- cache metadata and timestamps.

The database remains inside `.cache` and is restored by GitHub Actions cache. It is not committed into `output/`.

### Metadata enrichment engine

Updated:

`src/metadata_enrichment.py`

The enrichment flow is now:

1. Normalize the programme title.
2. Check in-run memo.
3. Check SQLite title cache.
4. Check learned aliases.
5. Only for unknown titles, resolve through TMDb.
6. Save the result back into SQLite.
7. Fill programme metadata from SQLite/TMDb/IMDb dataset.

This substantially reduces repeated external lookups over time.

### Request budget behavior

`METADATA_MAX_REQUESTS` is now treated as a budget for new unique metadata title lookups, not as a raw HTTP request counter.

This prevents one difficult title from consuming multiple units of the user-facing lookup budget through repeated TMDb attempts.

Default workflow value:

`METADATA_MAX_REQUESTS: "20000"`

### Human-readable programme description

v11.0 no longer exposes technical IMDb IDs such as `tt2283336` in the visible programme description.

Generated descriptions follow this structure:

`Жанр: Боевик, Комедия, Фантастика.`

`Описание фильма или сериала.`

`IMDb 5.6/10 · 162 195 голосов`

If the source EPG already contains a useful description, the builder preserves it instead of replacing it with TMDb overview text.

### XMLTV categories

Resolved genres are added as XMLTV `<category>` elements.

Existing categories are preserved and duplicate categories are not added.

### IMDb

IMDb ratings and vote counts continue to come from the local IMDb dataset path used by the existing project.

IMDb identity is kept technically through the programme URL and internal metadata, while the visible description remains user-friendly.

### Series reuse

Episodes of the same fiction series are collapsed to a shared metadata identity where safe.

For example, entries such as:

- `След (Нарциссы)`
- `След (Очередь)`
- `След (Год спустя)`

reuse the same series metadata instead of performing a new external lookup for every episode.

### Quality guards

Updated:

`src/metadata_quality_patch.py`

Precision safeguards include:

- reject unsafe transliteration matches;
- preserve significant sequel/part numbers;
- reject transliteration when a meaningful number disappears;
- prevent dangerous `series-root` collapse when a dotted suffix may represent a real subtitle;
- revalidate legacy positive cache rows that do not contain enough quality metadata.

A missed match is preferred over attaching metadata from the wrong film or series.

### Builder integration

Updated:

`src/builder.py`

The builder now logs explicit metadata phase start/completion and reports SQLite/title lookup counters.

The published metadata report remains:

`output/metadata-enrichment.json`

and the existing CSV reporting pipeline remains available.

### Startup

Updated:

`run.py`

The quality patch is loaded before the builder:

```python
import src.metadata_quality_patch  # noqa: F401
from src.builder import build
```

This ensures v11 quality guards are active on every run.

### GitHub Actions

Updated:

`.github/workflows/update.yml`

Changes:

- workflow timeout increased to 90 minutes;
- metadata lookup budget set to 20000;
- `.cache` continues to be restored through GitHub Actions cache;
- cache step wording now explicitly includes SQLite metadata.

## Tests

New tests:

`tests/test_metadata_db.py`

Current result:

`12 passed`

Coverage includes:

- SQLite schema creation;
- title cache roundtrip;
- language-specific cache keys;
- negative cache rows;
- entity metadata storage;
- alias storage and yearless fallback;
- persistence after database reopen;
- database counters;
- WAL mode;
- context-manager commit behavior.

New tests:

`tests/test_metadata_enrichment_v110.py`

Current result:

`11 passed`

Coverage includes:

- genre + overview + IMDb rendering;
- no visible `tt...` IMDb ID;
- preservation of provider description;
- no duplicate IMDb suffixes;
- XMLTV genre categories;
- title cleanup;
- episode identity reuse;
- language filtering;
- full enrichment through SQLite;
- second-run cache hit without TMDb;
- one lookup for multiple episodes;
- unique-title lookup budget behavior.

## Files added or replaced

- `src/metadata_db.py`
- `src/metadata_enrichment.py`
- `src/metadata_quality_patch.py`
- `src/builder.py`
- `run.py`
- `.github/workflows/update.yml`
- `tests/test_metadata_db.py`
- `tests/test_metadata_enrichment_v110.py`
- `RELEASE_NOTES_V11.0.md`

## First run

The first v11 run can still be significantly slower than later runs because SQLite must learn titles that are not yet known locally.

Subsequent runs should increasingly resolve programmes from `.cache/metadata.sqlite3` without TMDb lookups.

## Expected operational behavior

The intended long-term behavior is:

`new title -> resolve once -> store in SQLite -> reuse on future EPG runs`

This means the local metadata knowledge base gradually grows with the actual films and series that appear in the user's IPTV EPG rather than attempting to mirror the full IMDb catalog.
