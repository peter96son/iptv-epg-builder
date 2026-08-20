# IPTV EPG Builder v13.0 — Stage 5

Rich viewer-facing programme cards.

The final XMLTV description can now contain:
- year;
- runtime;
- country;
- localized genres;
- original title when useful;
- the best available provider/TMDb overview;
- IMDb rating and vote count.

Technical IMDb IDs are never written into the visible description.

The same data is also emitted in standard XMLTV fields where possible:
`date`, `length units="minutes"`, `country`, `category`, `rating`, and the
machine-readable IMDb `url`.

IMDb English genres from the local bulk database are translated to Russian for
the TV display.

Provider descriptions are preserved when they contain useful prose. Tiny
technical stubs such as `Фильм` are replaced by a substantially richer overview.

Rendering is idempotent: repeated Update EPG runs do not duplicate generated
genre/rating/fact lines.

Preserve `data/metadata.sqlite3.gz`. Migration to schema v6 is automatic.
