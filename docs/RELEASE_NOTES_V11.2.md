# IPTV EPG Builder v11.2

Hybrid reliability release: v11 SQLite architecture plus the strongest reliability ideas reviewed from the alternate v10.0.2 implementation.

## Changes

- Preserve a verified IMDb identity when genres/overview are missing.
- `needs_display_refresh` refreshes display metadata opportunistically instead of discarding the title identity.
- Failed display refresh falls back to the already-verified cached identity.
- Graceful SIGTERM handling: metadata enrichment winds down, checkpoints SQLite and returns a valid result.
- Metadata report now includes stop reason and remaining HTTP/title budgets.
- Large XMLTV payloads spill to temporary disk after indexing.
- Spilled XMLTV is parsed directly from disk; it is not loaded back as one large bytes object.
- XMLTV iterparse continues clearing the root to avoid retaining cleared programme nodes.
- Existing v11.1 protections remain: hard HTTP budget, metadata deadline, periodic SQLite checkpoints,
  bounded source download phase, short TMDb retries, cache restore/save split with `if: always()`.

## Validation

This release adds tests for:
- preserving trusted legacy IMDb identity;
- deferred display refresh;
- actual disk spill;
- graceful-stop telemetry.
