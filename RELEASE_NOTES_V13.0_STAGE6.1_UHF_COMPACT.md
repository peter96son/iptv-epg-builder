# v13.0 Stage 6.1 — UHF compact programme card

For enriched fiction, UHF output is now optimized for its limited visible rows:

- title becomes `Title (year) · IMDb x.x`;
- `date`, `category`, `country`, and `length` are removed from programme XML;
- `<desc>` contains only the best plot/description;
- machine-readable IMDb `<rating>`, `<url>`, poster `<icon>`, and artwork `<image>` remain.

Rich year/genre/runtime/country metadata is still retained in `metadata.sqlite3`
for the future native player.

The channel display-name is intentionally unchanged because UHF renders that row
from channel metadata and blanking it risks breaking channel display/mapping.
