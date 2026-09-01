IPTV EPG Builder v15.0 — Stability / Source Chains

This is a cumulative architecture fix, not another channel-by-channel patch.

Core rules:
1. hard_pin is now a real restriction. Generic rescue sources cannot bypass it.
2. For a restricted channel, every explicitly listed source is its allowed fallback chain.
   hard_pin=1 activates restriction; hard_pin=0 rows remain allowed fallbacks.
3. v15 source chains are stored separately in data/source_policy_v15.csv so the
   accumulated historical source_pins.csv is not rewritten or lost.
4. Premiere Group critical channels prefer premiere-group-dedicated and fall back
   only to historically verified Gabbarit feeds.
5. 4ever keeps exact identities and uses IPTVX -> Openbox -> Gabbarit fallback sources.
6. The v14.12 12-hour destructive horizon filter is removed. XMLTVSource already
   requires current/upcoming usable programmes. Short rolling-window guides remain
   publishable and are reported as EXPIRING_SOON instead of being deleted.
7. Update EPG runs every 3 hours to reduce the chance that short rolling feeds expire
   between normal builds.
8. NO_PROGRAMMES and STALE remain fatal in final horizon QA.
9. Critical Premiere/4ever/KLI/BCU channels are added to the diagnostics watchlist.

Existing cumulative behavior is preserved: Ukrainian hard exclusions, categories,
metadata SQLite, UHF/UniPlayer Worker mapping, BCU/KLI verified pins, exact HD channel
identity, title normalization, IMDb/TMDb metadata and all existing source feeds.

EPG source set preserved from the repository. v15 de-duplicates equivalent physical downloads:
- premiere-group-dedicated
- Teleguide (single physical feed; duplicate alias skipped)
- m3u-edit-all-rescue
- gabbarit-current + distinct gabbarit-mirror (duplicate gabbarit-primary endpoint skipped)
- epgone-full-movie-rescue
plus the existing provider, IPTVX, Openbox, Runigma, EPG.PW, EPG.ONE, EPGShare,
KLI, BCU, Cineman, MiniMax and other configured sources.

Install: overwrite repository root with this ZIP, commit, run Update EPG once.

v15.0.2 control fix:
- duplicate physical feeds are merged, not merely skipped;
- group scopes are unioned, so retained gabbarit-current keeps USSR eligibility inherited from the duplicate movie-rescue definition;
- first source name/order remains authoritative.
