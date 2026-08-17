const VERSION = "1.5.0";

const DEFAULT_EPG_URL =
  "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/epg.xml.gz";

const DEFAULT_MAPPING_URL =
  "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/uhf-mapping.json";

const PROTECTED_GROUPS = new Set([
  "Кино",
  "Кинозалы",
  "Кино 4K",
  "Кинозалы UA"
]);

function rewriteHeader(line, epgUrl) {
  if (!line.startsWith("#EXTM3U")) return line;

  if (/\burl-tvg\s*=\s*"[^"]*"/i.test(line)) {
    return line.replace(
      /\burl-tvg\s*=\s*"[^"]*"/i,
      `url-tvg="${epgUrl}"`
    );
  }

  if (/\bx-tvg-url\s*=\s*"[^"]*"/i.test(line)) {
    return line.replace(
      /\bx-tvg-url\s*=\s*"[^"]*"/i,
      `x-tvg-url="${epgUrl}"`
    );
  }

  return `${line.trimEnd()} url-tvg="${epgUrl}"`;
}

function rewriteTvgId(line, newId) {
  if (!newId) return line;

  if (/\btvg-id\s*=\s*"[^"]*"/i.test(line)) {
    return line.replace(
      /\btvg-id\s*=\s*"[^"]*"/i,
      `tvg-id="${newId}"`
    );
  }

  const firstSpace = line.indexOf(" ");

  if (firstSpace !== -1) {
    return (
      `${line.slice(0, firstSpace)} ` +
      `tvg-id="${newId}"` +
      line.slice(firstSpace)
    );
  }

  const comma = line.indexOf(",");

  if (comma !== -1) {
    return (
      `${line.slice(0, comma)} ` +
      `tvg-id="${newId}"` +
      line.slice(comma)
    );
  }

  return line;
}

function removeAttribute(line, attribute) {
  const re = new RegExp(
    `\\s+${attribute}\\s*=\\s*"[^"]*"`,
    "ig"
  );

  return line.replace(re, "");
}

function getAttribute(line, attribute) {
  const re = new RegExp(
    `\\b${attribute}\\s*=\\s*"([^"]*)"`,
    "i"
  );

  const match = line.match(re);
  return match ? match[1].trim() : "";
}

function getChannelName(line) {
  const comma = line.indexOf(",");

  return comma >= 0
    ? line.slice(comma + 1).trim()
    : "";
}

function getGroupFromBlock(blockLines) {
  for (const line of blockLines) {
    if (line.startsWith("#EXTGRP:")) {
      return line.slice("#EXTGRP:".length).trim();
    }
  }

  return "";
}

function hasPlaceholderTvgId(line) {
  const tvgId = getAttribute(line, "tvg-id");

  return /^no_epg(?:_|$)/i.test(tvgId);
}

function cleanUnmatchedChannel(line) {
  line = removeAttribute(line, "tvg-id");
  line = removeAttribute(line, "tvg-name");

  return line;
}

function rewritePlaylist(m3u, mapping, epgUrl) {
  const lines = m3u.split(/\r?\n/);
  const out = [];

  let totalChannels = 0;
  let matched = 0;
  let protectedUnmatched = 0;
  let placeholderCleaned = 0;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    if (line.startsWith("#EXTM3U")) {
      out.push(rewriteHeader(line, epgUrl));
      continue;
    }

    if (!line.startsWith("#EXTINF")) {
      out.push(line);
      continue;
    }

    /*
     * A provider channel is a block:
     *
     *   #EXTINF:...
     *   #EXTGRP:...
     *   stream URL
     *
     * Some providers may include extra metadata lines between
     * #EXTINF and the stream URL, so collect the whole block
     * until the next #EXTINF or end of file.
     */

    const blockLines = [line];

    while (
      i + 1 < lines.length &&
      !lines[i + 1].startsWith("#EXTINF") &&
      !lines[i + 1].startsWith("#EXTM3U")
    ) {
      blockLines.push(lines[++i]);
    }

    totalChannels++;

    const channelName =
      getChannelName(blockLines[0]);

    const group =
      getGroupFromBlock(blockLines);

    const newId =
      mapping[channelName];

    /*
     * MATCHED CHANNEL
     *
     * Generated mapping is authoritative.
     * Replace the provider tvg-id with the verified XMLTV ID.
     */

    if (newId) {
      blockLines[0] =
        rewriteTvgId(blockLines[0], newId);

      matched++;

      out.push(...blockLines);
      continue;
    }

    /*
     * UNMATCHED PROTECTED GROUP
     *
     * Do not trust provider EPG hints for unmatched cinema
     * and virtual/FAST channels. Remove both tvg-id and
     * tvg-name so IPTV players cannot attach an unrelated EPG.
     */

    if (PROTECTED_GROUPS.has(group)) {
      blockLines[0] =
        cleanUnmatchedChannel(blockLines[0]);

      protectedUnmatched++;

      out.push(...blockLines);
      continue;
    }

    /*
     * PLACEHOLDER IDs
     *
     * IDs such as no_epg_cinema and no_epg_mult are not real
     * XMLTV channel IDs. Remove them for any unmatched channel,
     * regardless of category.
     */

    if (hasPlaceholderTvgId(blockLines[0])) {
      blockLines[0] =
        cleanUnmatchedChannel(blockLines[0]);

      placeholderCleaned++;
    }

    out.push(...blockLines);
  }

  return {
    playlist: out.join("\n"),
    totalChannels,
    matched,
    protectedUnmatched,
    placeholderCleaned
  };
}

function notFound() {
  return new Response(
    "Not found",
    {
      status: 404,
      headers: {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"
      }
    }
  );
}

function jsonResponse(data, status = 200) {
  return new Response(
    JSON.stringify(data, null, 2),
    {
      status,
      headers: {
        "Content-Type":
          "application/json; charset=utf-8",

        "Cache-Control":
          "no-store",

        "X-Content-Type-Options":
          "nosniff"
      }
    }
  );
}

export default {
  async fetch(request, env, ctx) {
    const url =
      new URL(request.url);

    const epgUrl =
      env.EPG_URL ||
      DEFAULT_EPG_URL;

    const mappingUrl =
      env.MAPPING_URL ||
      DEFAULT_MAPPING_URL;

    /*
     * HEALTH
     */

    if (url.pathname === "/health") {
      if (!env.PLAYLIST_URL) {
        return jsonResponse(
          {
            ok: false,
            version: VERSION,
            error:
              "PLAYLIST_URL is not configured"
          },
          500
        );
      }

      try {
        const response =
          await fetch(
            env.PLAYLIST_URL,
            {
              method: "GET",

              headers: {
                "User-Agent":
                  `UHF-Private-Playlist-Worker/${VERSION}`
              }
            }
          );

        return jsonResponse({
          ok: response.ok,
          version: VERSION,
          playlist_status:
            response.status,
          epg_url:
            epgUrl,
          mapping_url:
            mappingUrl
        });

      } catch (error) {
        return jsonResponse(
          {
            ok: false,
            version: VERSION,
            error:
              String(error)
          },
          500
        );
      }
    }

    /*
     * EPG
     */

    if (url.pathname === "/epg") {
      return Response.redirect(
        epgUrl,
        302
      );
    }

    /*
     * PLAYLIST
     */

    const isTv = url.pathname === "/tv";
    const isDownload = url.pathname === "/download";

    if (!isTv && !isDownload) {
      return notFound();
    }

    if (!env.PLAYLIST_URL) {
      return new Response(
        "PLAYLIST_URL is not configured",
        {
          status: 500,
          headers: {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
          }
        }
      );
    }

    /*
     * New cache key for v1.5.0.
     *
     * This prevents Cloudflare from serving an older rewritten playlist.
     */

    const cache =
      caches.default;

    const cacheKey =
      new Request(
        url.origin +
        "/tv-cache-v150",
        {
          method: "GET"
        }
      );

    const cached =
      await cache.match(
        cacheKey
      );

    if (cached) {
      if (isDownload) {
        const headers = new Headers(cached.headers);
        headers.set(
          "Content-Disposition",
          'attachment; filename="playlist.m3u"'
        );
        return new Response(cached.body, {
          status: cached.status,
          headers
        });
      }
      return cached;
    }

    /*
     * DOWNLOAD SOURCE PLAYLIST + MAPPING
     */

    const [
      playlistResponse,
      mappingResponse
    ] =
      await Promise.all([
        fetch(
          env.PLAYLIST_URL,
          {
            headers: {
              "User-Agent":
                `UHF-Private-Playlist-Worker/${VERSION}`
            }
          }
        ),

        fetch(
          mappingUrl,
          {
            headers: {
              "User-Agent":
                `UHF-Private-Playlist-Worker/${VERSION}`
            }
          }
        )
      ]);

    if (!playlistResponse.ok) {
      return new Response(
        `Upstream playlist error: ${playlistResponse.status}`,
        {
          status: 502,
          headers: {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
          }
        }
      );
    }

    /*
     * LOAD VERIFIED MAPPING
     */

    let mapping = {};
    let mappingLoaded = false;

    if (mappingResponse.ok) {
      try {
        const payload =
          await mappingResponse.json();

        mapping =
          payload.channels || {};

        mappingLoaded = true;

      } catch (_) {
        mapping = {};
      }
    }

    /*
     * REWRITE PLAYLIST
     */

    const original =
      await playlistResponse.text();

    const result =
      rewritePlaylist(
        original,
        mapping,
        epgUrl
      );

    const rewritten =
      result.playlist;

    const responseHeaders = {
      "Content-Type":
        "application/x-mpegURL; charset=utf-8",

      "Content-Disposition":
        isDownload
          ? 'attachment; filename="playlist.m3u"'
          : 'inline; filename="playlist.m3u"',

      "Cache-Control":
        "private, max-age=0",

      "X-Content-Type-Options":
        "nosniff",

      "Referrer-Policy":
        "no-referrer",

      "X-EPG-Worker-Version":
        VERSION,

      "X-EPG-Mapping-Loaded":
        String(mappingLoaded),

      "X-EPG-Total-Channels":
        String(result.totalChannels),

      "X-EPG-Matched":
        String(result.matched),

      "X-EPG-Protected-Unmatched":
        String(result.protectedUnmatched),

      "X-EPG-Placeholder-Cleaned":
        String(result.placeholderCleaned)
    };

    const response =
      new Response(
        rewritten,
        {
          status: 200,
          headers:
            responseHeaders
        }
      );

    /*
     * CACHE FOR 15 MINUTES
     */

    ctx.waitUntil(
      cache.put(
        cacheKey,

        new Response(
          rewritten,
          {
            status: 200,

            headers: {
              ...responseHeaders,

              "Content-Disposition":
                'inline; filename="playlist.m3u"',

              "Cache-Control":
                "s-maxage=900"
            }
          }
        )
      )
    );

    return response;
  }
};

export {
  rewriteHeader,
  rewriteTvgId,
  rewritePlaylist,
  cleanUnmatchedChannel,
  getGroupFromBlock,
  hasPlaceholderTvgId
};
