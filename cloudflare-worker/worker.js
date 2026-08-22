const VERSION = "2.1.0";
const DEFAULT_EPG_URL = "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/epg.xml.gz";
const DEFAULT_MAPPING_URL = "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/uhf-mapping.json";
const DEFAULT_RULES_URL = "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/data/playlist_rules.json";
const PROTECTED_GROUPS = new Set(["Кино","Кинозалы","Кино 4K","Кинозалы UA"]);

function rewriteHeader(line, epgUrl) {
  if (!line.startsWith("#EXTM3U")) return line;
  if (/\burl-tvg\s*=\s*"[^"]*"/i.test(line)) return line.replace(/\burl-tvg\s*=\s*"[^"]*"/i, `url-tvg="${epgUrl}"`);
  if (/\bx-tvg-url\s*=\s*"[^"]*"/i.test(line)) return line.replace(/\bx-tvg-url\s*=\s*"[^"]*"/i, `x-tvg-url="${epgUrl}"`);
  return `${line.trimEnd()} url-tvg="${epgUrl}"`;
}
function rewriteTvgId(line,newId){
  if(!newId) return line;
  if(/\btvg-id\s*=\s*"[^"]*"/i.test(line)) return line.replace(/\btvg-id\s*=\s*"[^"]*"/i,`tvg-id="${newId}"`);
  const firstSpace=line.indexOf(" ");
  if(firstSpace!==-1) return `${line.slice(0,firstSpace)} tvg-id="${newId}"${line.slice(firstSpace)}`;
  const comma=line.indexOf(",");
  if(comma!==-1) return `${line.slice(0,comma)} tvg-id="${newId}"${line.slice(comma)}`;
  return line;
}
function removeAttribute(line,attribute){ return line.replace(new RegExp(`\\s+${attribute}\\s*=\\s*"[^"]*"`,"ig"),""); }
function getAttribute(line,attribute){ const m=line.match(new RegExp(`\\b${attribute}\\s*=\\s*"([^"]*)"`,"i")); return m?m[1].trim():""; }
function getChannelName(line){ const c=line.indexOf(","); return c>=0?line.slice(c+1).trim():""; }
function getGroupFromBlock(lines){ for(const l of lines) if(l.startsWith("#EXTGRP:")) return l.slice(8).trim(); return ""; }
function rewriteGroupInBlock(lines,newGroup){
  if(!newGroup) return lines;
  let done=false;
  const out=lines.map(l=>{ if(l.startsWith("#EXTGRP:")){ done=true; return `#EXTGRP:${newGroup}`;} return l;});
  if(!done) out.splice(1,0,`#EXTGRP:${newGroup}`);
  return out;
}
function hasPlaceholderTvgId(line){ return /^no_epg(?:_|$)/i.test(getAttribute(line,"tvg-id")); }
function cleanUnmatchedChannel(line){ return removeAttribute(removeAttribute(line,"tvg-id"),"tvg-name"); }
function normalizeRules(p){ return {excludeGroups:new Set(Array.isArray(p?.exclude_groups)?p.exclude_groups:[]),groupOverrides:(p&&typeof p.group_overrides==="object"&&p.group_overrides)||{}}; }

function rewritePlaylist(m3u,mapping,epgUrl,rulesPayload={}){
  const lines=m3u.split(/\r?\n/),out=[],rules=normalizeRules(rulesPayload);
  let totalChannels=0,matched=0,protectedUnmatched=0,placeholderCleaned=0,excluded=0,regrouped=0;
  for(let i=0;i<lines.length;i++){
    let line=lines[i];
    if(line.startsWith("#EXTM3U")){ out.push(rewriteHeader(line,epgUrl)); continue; }
    if(!line.startsWith("#EXTINF")){ out.push(line); continue; }
    let block=[line];
    while(i+1<lines.length&&!lines[i+1].startsWith("#EXTINF")&&!lines[i+1].startsWith("#EXTM3U")) block.push(lines[++i]);
    totalChannels++;
    const name=getChannelName(block[0]), originalGroup=getGroupFromBlock(block);
    if(rules.excludeGroups.has(originalGroup)){ excluded++; continue; }
    const override=rules.groupOverrides[name];
    if(override){ block=rewriteGroupInBlock(block,override); regrouped++; }
    const group=getGroupFromBlock(block), newId=mapping[name];
    if(newId){ block[0]=rewriteTvgId(block[0],newId); matched++; out.push(...block); continue; }
    if(PROTECTED_GROUPS.has(group)){ block[0]=cleanUnmatchedChannel(block[0]); protectedUnmatched++; out.push(...block); continue; }
    if(hasPlaceholderTvgId(block[0])){ block[0]=cleanUnmatchedChannel(block[0]); placeholderCleaned++; }
    out.push(...block);
  }
  return {playlist:out.join("\n"),totalChannels,matched,protectedUnmatched,placeholderCleaned,excluded,regrouped};
}
function notFound(){ return new Response("Not found",{status:404,headers:{"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}}); }
function jsonResponse(data,status=200){ return new Response(JSON.stringify(data,null,2),{status,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}}); }

export default {
 async fetch(request,env,ctx){
  const url=new URL(request.url), epgUrl=env.EPG_URL||DEFAULT_EPG_URL, mappingUrl=env.MAPPING_URL||DEFAULT_MAPPING_URL, rulesUrl=env.RULES_URL||DEFAULT_RULES_URL;
  if(url.pathname==="/health"){
    if(!env.PLAYLIST_URL) return jsonResponse({ok:false,version:VERSION,error:"PLAYLIST_URL is not configured"},500);
    try{ const r=await fetch(env.PLAYLIST_URL,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}});
      return jsonResponse({ok:r.ok,version:VERSION,playlist_status:r.status,epg_url:epgUrl,mapping_url:mappingUrl,rules_url:rulesUrl});
    }catch(e){ return jsonResponse({ok:false,version:VERSION,error:String(e)},500); }
  }
  if(url.pathname==="/epg") return Response.redirect(epgUrl,302);
  const isTv=url.pathname==="/tv",isDownload=url.pathname==="/download",forceFresh=url.searchParams.get("fresh")==="1";
  if(!isTv&&!isDownload) return notFound();
  if(!env.PLAYLIST_URL) return new Response("PLAYLIST_URL is not configured",{status:500,headers:{"Cache-Control":"no-store"}});
  const cache=caches.default, cacheKey=new Request(url.origin+"/tv-cache-v210",{method:"GET"}), cached=forceFresh?null:await cache.match(cacheKey);
  if(cached){ if(isDownload){ const h=new Headers(cached.headers); h.set("Content-Disposition",'attachment; filename="playlist.m3u"'); return new Response(cached.body,{status:cached.status,headers:h}); } return cached; }
  const [pr,mr,rr]=await Promise.all([
    fetch(env.PLAYLIST_URL,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}}),
    fetch(mappingUrl,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}}),
    fetch(rulesUrl,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}})
  ]);
  if(!pr.ok) return new Response(`Upstream playlist error: ${pr.status}`,{status:502,headers:{"Cache-Control":"no-store"}});
  let mapping={},mappingLoaded=false,rules={},rulesLoaded=false;
  if(mr.ok){ try{ const p=await mr.json(); mapping=p.channels||{}; mappingLoaded=true;}catch(_){}}
  if(rr.ok){ try{ rules=await rr.json(); rulesLoaded=true;}catch(_){}}
  const original=await pr.text(), result=rewritePlaylist(original,mapping,epgUrl,rules), rewritten=result.playlist;
  const headers={"Content-Type":"application/x-mpegURL; charset=utf-8","Content-Disposition":isDownload?'attachment; filename="playlist.m3u"':'inline; filename="playlist.m3u"',"Cache-Control":"private, max-age=0","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","X-EPG-Worker-Version":VERSION,"X-EPG-Mapping-Loaded":String(mappingLoaded),"X-Playlist-Rules-Loaded":String(rulesLoaded),"X-EPG-Total-Channels":String(result.totalChannels),"X-EPG-Matched":String(result.matched),"X-Playlist-Excluded":String(result.excluded),"X-Playlist-Regrouped":String(result.regrouped),"X-EPG-Cache":forceFresh?"bypass":"miss"};
  const response=new Response(rewritten,{status:200,headers});
  if(!forceFresh) ctx.waitUntil(cache.put(cacheKey,new Response(rewritten,{status:200,headers:{...headers,"Content-Disposition":'inline; filename="playlist.m3u"',"Cache-Control":"s-maxage=900"}})));
  return response;
 }
};

export {rewriteHeader,rewriteTvgId,rewritePlaylist,rewriteGroupInBlock,cleanUnmatchedChannel,getGroupFromBlock,hasPlaceholderTvgId,normalizeRules};
