# IPTV EPG Builder v11.2.2

Fixes a display-enrichment bug for programmes that already had IMDb identity.

Previously such programmes could stop at the IMDb ratings dataset, which provides
rating and vote count but no genre or overview. v11.2.2 now resolves TMDb directly
by the known IMDb ID and stores overview/genres in SQLite.
