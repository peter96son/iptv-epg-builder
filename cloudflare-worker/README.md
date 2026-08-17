# Private UHF playlist Worker

The Worker exposes one stable HTTPS M3U URL for UHF without publishing the
provider's stream-bearing M3U to GitHub.

Required Worker secrets:
- `PLAYLIST_URL`
- `ACCESS_TOKEN`

Final UHF URL:
`https://<your-worker>.workers.dev/playlist/<ACCESS_TOKEN>`

The Worker:
- fetches the current provider M3U;
- fetches safe TVG-ID mappings from GitHub;
- points the playlist to the merged GitHub EPG;
- preserves stream URLs, ordering, channel names, logos and #EXTGRP categories;
- rewrites only verified TVG IDs;
- caches the generated playlist for 15 minutes.
