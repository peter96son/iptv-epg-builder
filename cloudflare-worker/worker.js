const DEFAULT_EPG_URL =
  "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/epg.xml.gz";

const DEFAULT_MAPPING_URL =
  "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/uhf-mapping.json";

function rewriteHeader(line, epgUrl) {
  if (!line.startsWith("#EXTM3U")) return line;

  if (/\burl-tvg\s*=\s*"[^"]*"/i.test(line)) {
    return line.replace(/\burl-tvg\s*=\s*"[^"]*"/i, `url-tvg="${epgUrl}"`);
  }
  if (/\bx-tvg-url\s*=\s*"[^"]*"/i.test(line)) {
    return line.replace(/\bx-tvg-url\s*=\s*"[^"]*"/i, `x-tvg-url="${epgUrl}"`);
  }
  return `${line.trimEnd()} url-tvg="${epgUrl}"`;
}

function rewriteTvgId(extinf, newId) {
  if (!newId) return extinf;

  const existing = extinf.match(/\btvg-id\s*=\s*"([^"]*)"/i);
  if (existing) {
    if (existing[1] === newId) return extinf;
    return extinf.replace(/\btvg-id\s*=\s*"[^"]*"/i, `tvg-id="${newId}"`);
  }

  const firstSpace = extinf.indexOf(" ");
  if (firstSpace !== -1) {
    return `${extinf.slice(0, firstSpace)} tvg-id="${newId}"${extinf.slice(firstSpace)}`;
  }

  const comma = extinf.indexOf(",");
  if (comma !== -1) {
    return `${extinf.slice(0, comma)} tvg-id="${newId}"${extinf.slice(comma)}`;
  }

  return extinf;
}

function rewritePlaylist(m3u, mapping, epgUrl) {
  const out = [];

  for (let line of m3u.split(/\r?\n/)) {
    if (line.startsWith("#EXTM3U")) {
      out.push(rewriteHeader(line, epgUrl));
      continue;
    }

    if (line.startsWith("#EXTINF")) {
      const comma = line.indexOf(",");
      const name = comma >= 0 ? line.slice(comma + 1).trim() : "";
      const newId = mapping[name];
      if (newId) line = rewriteTvgId(line, newId);
    }

    out.push(line);
  }

  return out.join("\n");
}

function notFound() {
  return new Response("Not found", {
    status: 404,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    }
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);

    if (
      parts.length !== 2 ||
      parts[0] !== "playlist" ||
      !env.ACCESS_TOKEN ||
      parts[1] !== env.ACCESS_TOKEN
    ) {
      return notFound();
    }

    if (!env.PLAYLIST_URL) {
      return new Response("PLAYLIST_URL secret is not configured", { status: 500 });
    }

    const epgUrl = env.EPG_URL || DEFAULT_EPG_URL;
    const mappingUrl = env.MAPPING_URL || DEFAULT_MAPPING_URL;

    // Cache key includes the bearer token path.
    const cache = caches.default;
    const cacheKey = new Request(request.url, { method: "GET" });
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const [playlistResponse, mappingResponse] = await Promise.all([
      fetch(env.PLAYLIST_URL, {
        headers: { "User-Agent": "UHF-Private-Playlist-Worker/1.4" }
      }),
      fetch(mappingUrl, {
        headers: { "User-Agent": "UHF-Private-Playlist-Worker/1.4" }
      })
    ]);

    if (!playlistResponse.ok) {
      return new Response(`Upstream playlist error: ${playlistResponse.status}`, {
        status: 502
      });
    }

    let mapping = {};
    if (mappingResponse.ok) {
      try {
        const payload = await mappingResponse.json();
        mapping = payload.channels || {};
      } catch (_) {
        mapping = {};
      }
    }

    const original = await playlistResponse.text();
    const rewritten = rewritePlaylist(original, mapping, epgUrl);

    const responseHeaders = {
      "Content-Type": "application/x-mpegURL; charset=utf-8",
      "Content-Disposition": 'inline; filename="playlist.m3u"',
      "Cache-Control": "private, max-age=0",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer"
    };

    ctx.waitUntil(
      cache.put(
        cacheKey,
        new Response(rewritten, {
          status: 200,
          headers: {
            ...responseHeaders,
            "Cache-Control": "s-maxage=900"
          }
        })
      )
    );

    return new Response(rewritten, { status: 200, headers: responseHeaders });
  }
};

export { rewriteHeader, rewriteTvgId, rewritePlaylist };
