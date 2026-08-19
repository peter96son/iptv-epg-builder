# IPTV EPG Builder v11.2.1

Small reliability cleanup after external review of v11.2.

## Fixed

- Fixed a file-descriptor leak when parsing spilled gzip XMLTV sources.
  Closing the returned gzip stream now also closes the owned raw file handle.
- Release every XMLTV source payload after programme extraction and before
  metadata enrichment, including sources smaller than the 4 MB spill threshold.
- Raised `EPG_SOURCE_TIMEOUT_CAP` from 45s to 90s to avoid dropping slow-but-valid
  providers before their first byte.
- Raised the source-phase deadline from 1200s to 1500s, while keeping the global
  90-minute job timeout and the 35-minute metadata deadline.

## Validation

The full test suite is run before packaging this release.
