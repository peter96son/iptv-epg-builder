v15.2 — persistent live source catalog

After v15.1 source selection, this version reads the selector's MISSING rows
and redownloads only the affected source feeds.

It commits output/source-catalog-v15.json through the existing `git add -A output/`.

The catalog contains:
- real live XMLTV channel IDs;
- display-name aliases;
- future horizon when exposed by the indexed source;
- the exact policy rows that were missing.

It does not store provider playlist URLs, stream URLs, or raw XMLTV payloads.

This gives future debugging a stable evidence file in GitHub instead of relying
on transient runner logs or guessing source IDs.
