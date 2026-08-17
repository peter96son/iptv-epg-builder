# Cloudflare Worker — v1.5.0

This Worker privately delivers the current IPTV Online playlist without publishing provider stream URLs to GitHub.

## Routes

- `/tv` — rewritten M3U for IPTV players (`Content-Disposition: inline`)
- `/download` — same M3U as a browser download (`playlist.m3u`)
- `/epg` — redirects to the generated `epg.xml.gz`
- `/health` — checks the configured private upstream playlist

## Cloudflare variables

Required:
- `PLAYLIST_URL` — private provider M3U URL

Optional overrides:
- `EPG_URL`
- `MAPPING_URL`

`ACCESS_TOKEN` is no longer used.

## Safety behavior

The Worker loads `output/uhf-mapping.json` and uses those verified IDs for matched channels.

For unmatched channels in protected groups:
- `Кино`
- `Кинозалы`
- `Кино 4K`
- `Кинозалы UA`

it removes both `tvg-id` and `tvg-name` while preserving the channel name, logo, `#EXTGRP` category and stream URL.

For all unmatched channels, dummy IDs beginning with `no_epg` are removed.

The playlist is cached for 15 minutes using a versioned cache key.
