# IPTV EPG Builder v13.0 — Stage 6

Programme artwork.

TMDb search/find objects already return `poster_path` and `backdrop_path`, so
Stage 6 captures those paths without adding a new HTTP request per matched title.

Artwork is persisted in the durable normalized metadata database and reused on
later EPG builds.

For programme-level XMLTV output:
- poster is emitted as `<icon src="...">` when the provider did not already
  supply a programme icon;
- poster is also emitted as `<image type="poster" size="3" orient="P" system="tmdb">`;
- backdrop is emitted as `<image type="backdrop" size="3" orient="L" system="tmdb">`.

This deliberately does not touch `<channel><icon>` channel logos.

Poster URLs use TMDb `w500`; backdrops use `w780`. The image files themselves
are not downloaded into GitHub, so the repository does not grow with artwork.

The XMLTV DTD supports programme icons and the richer image element. UHF's
public site does not currently document which programme-artwork element it
renders, so Stage 6 writes both standards-compatible forms for compatibility.

Preserve `data/metadata.sqlite3.gz`. Migration to schema v7 is automatic.
