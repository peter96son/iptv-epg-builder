const VERSION = "3.0.8-v14.10";
const DEFAULT_EPG_URL = "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/epg.xml.gz";
const DEFAULT_MAPPING_URL = "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/output/uhf-mapping.json";
const DEFAULT_RULES_URL = "https://raw.githubusercontent.com/peter96son/iptv-epg-builder/main/data/playlist_rules.json";
const PROTECTED_GROUPS = new Set(["Кино","Кинозалы","Кино 4K","Кинозалы UA"]);

// Hard safety blacklist. These feeds must never appear in the delivered playlist,
// even if playlist_rules.json fails to load or Cloudflare serves stale rule data.
const HARD_EXCLUDE_NAME_PREFIXES = [
  "cine+",
  "твоє кіно",
  "твоє кино",
  "твое кіно",
  "твое кино",
  "prokino",
  "1+1 кіно",
  "1+1 кино",
];

function isHardExcludedName(name){
  const n=normName(name);
  return HARD_EXCLUDE_NAME_PREFIXES.some(prefix =>
    n === prefix ||
    n.startsWith(prefix + " ") ||
    n.startsWith(prefix + "+") ||
    n.startsWith(prefix + "-")
  );
}

// v14: Serial Ukraine 1/2 are no longer hidden; user explicitly moved them to "Сериалы".
// Old Ukrainian cinema feeds remain conditionally hidden by stable provider play-id.
const CONDITIONAL_EXCLUDES = [
  {name:"1+1 Кіно", group:"Кино", playId:"2005"},
  {name:"Cine+ HD", group:"Кино", playId:"7996"},
  {name:"Cine+ Hit HD", group:"Кино", playId:"7995"},
  {name:"Cine+ Legend", group:"Кино", playId:"7993"},
  {name:"Твоє Кіно Хіт", group:"Кино", playId:"16"},
  {name:"Твоє Кіно Action", group:"Кино", playId:"28"},
  {name:"Твоє Кіно Relax", group:"Кино", playId:"48"},
];

function rewriteHeader(line, epgUrl) {
  if (!line.startsWith("#EXTM3U")) return line;
  let out=line;
  if (/\burl-tvg\s*=\s*"[^"]*"/i.test(out)) out=out.replace(/\burl-tvg\s*=\s*"[^"]*"/i, `url-tvg="${epgUrl}"`);
  else out=`${out.trimEnd()} url-tvg="${epgUrl}"`;
  if (/\bx-tvg-url\s*=\s*"[^"]*"/i.test(out)) out=out.replace(/\bx-tvg-url\s*=\s*"[^"]*"/i, `x-tvg-url="${epgUrl}"`);
  else out=`${out.trimEnd()} x-tvg-url="${epgUrl}"`;
  return out;
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
function rewriteTvgName(line,newName){
  if(!newName) return line;
  if(/\btvg-name\s*=\s*"[^"]*"/i.test(line)) return line.replace(/\btvg-name\s*=\s*"[^"]*"/i,`tvg-name="${newName}"`);
  const comma=line.indexOf(",");
  if(comma>=0) return `${line.slice(0,comma)} tvg-name="${newName}"${line.slice(comma)}`;
  return line;
}
function versionedEpgUrl(base,version){
  if(!version)return base;
  try{
    const u=new URL(base);
    u.searchParams.set("v",String(version).replace(/[^0-9A-Za-z_.:-]/g,""));
    return u.toString();
  }catch(_){return base;}
}
function rewriteChannelName(line,newName){
  if(!newName) return line;
  let out=line; const comma=out.indexOf(",");
  if(comma>=0) out=out.slice(0,comma+1)+newName;
  if(/\btvg-name\s*=\s*"[^"]*"/i.test(out)) out=out.replace(/\btvg-name\s*=\s*"[^"]*"/i,`tvg-name="${newName}"`);
  return out;
}
function removeAttribute(line,attribute){ return line.replace(new RegExp(`\\s+${attribute}\\s*=\\s*"[^"]*"`,"ig"),""); }
function getAttribute(line,attribute){ const m=line.match(new RegExp(`\\b${attribute}\\s*=\\s*"([^"]*)"`,"i")); return m?m[1].trim():""; }
function getChannelName(line){ const c=line.indexOf(","); return c>=0?line.slice(c+1).trim():""; }
function getGroupFromBlock(lines){ for(const l of lines) if(l.startsWith("#EXTGRP:")) return l.slice(8).trim(); return ""; }
function getStreamUrlFromBlock(lines){ for(const l of lines){const s=(l||"").trim();if(s&&!s.startsWith("#"))return s;}return ""; }
function getPlayId(url){ const m=String(url||"").match(/\/play\/(\d+)\//i); return m?m[1]:""; }
function shouldConditionallyExclude(name,group,streamUrl){
  const playId=getPlayId(streamUrl);
  return CONDITIONAL_EXCLUDES.some(r=>r.name===name && r.group===group && r.playId===playId);
}
function rewriteGroupInBlock(lines,newGroup){
  if(!newGroup)return lines;
  let extgrpDone=false;
  const out=lines.map((l,idx)=>{
    if(idx===0 && l.startsWith("#EXTINF")){
      if(/\bgroup-title\s*=\s*"[^"]*"/i.test(l)){
        l=l.replace(/\bgroup-title\s*=\s*"[^"]*"/i,`group-title="${newGroup}"`);
      } else {
        const comma=l.indexOf(",");
        if(comma>=0) l=`${l.slice(0,comma)} group-title="${newGroup}"${l.slice(comma)}`;
        else l=`${l} group-title="${newGroup}"`;
      }
    }
    if(l.startsWith("#EXTGRP:")){
      extgrpDone=true;
      return `#EXTGRP:${newGroup}`;
    }
    return l;
  });
  if(!extgrpDone) out.splice(1,0,`#EXTGRP:${newGroup}`);
  return out;
}
function hasPlaceholderTvgId(line){ return /^no_epg(?:_|$)/i.test(getAttribute(line,"tvg-id")); }
function cleanUnmatchedChannel(line){ return removeAttribute(removeAttribute(line,"tvg-id"),"tvg-name"); }
function normName(v){ return String(v||"").trim().toLocaleLowerCase().replace(/\s+/g," "); }
function normalizeRules(p){
  const groupOverrides=(p&&typeof p.group_overrides==="object"&&p.group_overrides)||{};
  const normalizedGroupOverrides={};
  for(const [k,v] of Object.entries(groupOverrides)) normalizedGroupOverrides[normName(k)]=v;
  return {
    excludeGroups:new Set(Array.isArray(p?.exclude_groups)?p.exclude_groups:[]),
    excludeNamePrefixes:(Array.isArray(p?.exclude_name_prefixes)?p.exclude_name_prefixes:[]).map(normName).filter(Boolean),
    groupOverrides,
    normalizedGroupOverrides,
    nameOverrides:(p&&typeof p.name_overrides==="object"&&p.name_overrides)||{}
  };
}
function shouldRuleExcludeName(name,rules){
  const n=normName(name);
  return rules.excludeNamePrefixes.some(prefix=>n===prefix||n.startsWith(prefix+" ")||n.startsWith(prefix+"+")||n.startsWith(prefix+"-"));
}
function rewritePlaylist(m3u,mapping,epgUrl,rulesPayload={}){
  const lines=m3u.split(/\r?\n/),out=[],rules=normalizeRules(rulesPayload);
  const normalizedMapping={};
  for(const [name,id] of Object.entries(mapping||{})){
    const key=normName(name);
    if(key && !normalizedMapping[key]) normalizedMapping[key]=id;
  }
  let totalChannels=0,matched=0,protectedUnmatched=0,placeholderCleaned=0,excluded=0,conditionalExcluded=0,regrouped=0,renamed=0;
  for(let i=0;i<lines.length;i++){
    let line=lines[i];
    if(line.startsWith("#EXTM3U")){out.push(rewriteHeader(line,epgUrl));continue;}
    if(!line.startsWith("#EXTINF")){out.push(line);continue;}
    let block=[line];
    while(i+1<lines.length&&!lines[i+1].startsWith("#EXTINF")&&!lines[i+1].startsWith("#EXTM3U"))block.push(lines[++i]);
    totalChannels++;
    const originalName=getChannelName(block[0]),originalGroup=getGroupFromBlock(block),streamUrl=getStreamUrlFromBlock(block);
    if(isHardExcludedName(originalName)||rules.excludeGroups.has(originalGroup)||shouldRuleExcludeName(originalName,rules)){excluded++;continue;}
    if(shouldConditionallyExclude(originalName,originalGroup,streamUrl)){conditionalExcluded++;continue;}

    const normalizedName=normName(originalName);
    const explicitOverride=rules.groupOverrides[originalName]||rules.normalizedGroupOverrides[normalizedName];
    // User policy: if the channel name itself contains "сериал" / "serial",
    // it belongs in the Series category unless an explicit override says otherwise.
    const automaticSeries=(normalizedName.includes("сериал") || /(^|[^a-z])serial([^a-z]|$)/i.test(normalizedName))
      ? "Сериалы" : "";
    const groupOverride=explicitOverride||automaticSeries;
    if(groupOverride){block=rewriteGroupInBlock(block,groupOverride);regrouped++;}

    const group=getGroupFromBlock(block),newId=mapping[originalName]||normalizedMapping[normalizedName];
    if(newId){
      block[0]=rewriteTvgId(block[0],newId);
      block[0]=rewriteTvgName(block[0],originalName);
      matched++;
    }
    else if(PROTECTED_GROUPS.has(group)){block[0]=cleanUnmatchedChannel(block[0]);protectedUnmatched++;}
    else if(hasPlaceholderTvgId(block[0])){block[0]=cleanUnmatchedChannel(block[0]);placeholderCleaned++;}

    const displayName=rules.nameOverrides[originalName];
    if(displayName){block[0]=rewriteChannelName(block[0],displayName);renamed++;}
    out.push(...block);
  }
  return {playlist:out.join("\n"),totalChannels,matched,protectedUnmatched,placeholderCleaned,excluded,conditionalExcluded,regrouped,renamed};
}
function notFound(){return new Response("Not found",{status:404,headers:{"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});}
function jsonResponse(data,status=200){return new Response(JSON.stringify(data,null,2),{status,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});}

export default {
 async fetch(request,env,ctx){
  const url=new URL(request.url),epgUrl=env.EPG_URL||DEFAULT_EPG_URL,mappingUrl=env.MAPPING_URL||DEFAULT_MAPPING_URL,rulesUrl=env.RULES_URL||DEFAULT_RULES_URL;
  if(url.pathname==="/health"){
    if(!env.PLAYLIST_URL)return jsonResponse({ok:false,version:VERSION,error:"PLAYLIST_URL is not configured"},500);
    try{const r=await fetch(env.PLAYLIST_URL,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}});
      return jsonResponse({ok:r.ok,version:VERSION,playlist_status:r.status,epg_url:epgUrl,mapping_url:mappingUrl,rules_url:rulesUrl});}
    catch(e){return jsonResponse({ok:false,version:VERSION,error:String(e)},500);}
  }
  if(url.pathname==="/epg")return Response.redirect(epgUrl,302);
  const isTv=url.pathname==="/tv",isDownload=url.pathname==="/download",forceFresh=url.searchParams.get("fresh")==="1";
  if(!isTv&&!isDownload)return notFound();
  if(!env.PLAYLIST_URL)return new Response("PLAYLIST_URL is not configured",{status:500,headers:{"Cache-Control":"no-store"}});
  const cache=caches.default,cacheKey=new Request(url.origin+"/tv-cache-v14-10",{method:"GET"}),cached=forceFresh?null:await cache.match(cacheKey);
  if(cached){if(isDownload){const h=new Headers(cached.headers);h.set("Content-Disposition",'attachment; filename="playlist.m3u"');return new Response(cached.body,{status:cached.status,headers:h});}return cached;}
  const [pr,mr,rr]=await Promise.all([
    fetch(env.PLAYLIST_URL,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}}),
    fetch(mappingUrl,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}}),
    fetch(rulesUrl,{headers:{"User-Agent":`UHF-Private-Playlist-Worker/${VERSION}`}})
  ]);
  if(!pr.ok)return new Response(`Upstream playlist error: ${pr.status}`,{status:502,headers:{"Cache-Control":"no-store"}});
  let mapping={},mappingLoaded=false,mappingVersion="",rules={},rulesLoaded=false;
  if(mr.ok){
    try{
      const p=await mr.json();
      mapping=p.channels||{};
      mappingVersion=p.generated_at||"";
      mappingLoaded=true;
    }catch(_){}
  }
  if(rr.ok){try{rules=await rr.json();rulesLoaded=true;}catch(_){}}
  const deliveryEpgUrl=versionedEpgUrl(epgUrl,mappingVersion);
  const original=await pr.text(),result=rewritePlaylist(original,mapping,deliveryEpgUrl,rules),rewritten=result.playlist;
  const headers={"Content-Type":"application/x-mpegURL; charset=utf-8","Content-Disposition":isDownload?'attachment; filename="playlist.m3u"':'inline; filename="playlist.m3u"',"Cache-Control":"private, max-age=0","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","X-EPG-Worker-Version":VERSION,"X-EPG-Mapping-Loaded":String(mappingLoaded),"X-EPG-Delivery-URL":deliveryEpgUrl,"X-Playlist-Rules-Loaded":String(rulesLoaded),"X-EPG-Total-Channels":String(result.totalChannels),"X-EPG-Matched":String(result.matched),"X-Playlist-Excluded":String(result.excluded),"X-Playlist-Conditional-Excluded":String(result.conditionalExcluded),"X-Playlist-Regrouped":String(result.regrouped),"X-Playlist-Renamed":String(result.renamed),"X-EPG-Cache":forceFresh?"bypass":"miss"};
  const response=new Response(rewritten,{status:200,headers});
  if(!forceFresh)ctx.waitUntil(cache.put(cacheKey,new Response(rewritten,{status:200,headers:{...headers,"Content-Disposition":'inline; filename="playlist.m3u"',"Cache-Control":"s-maxage=900"}})));
  return response;
 }
};
export {rewriteHeader,rewriteTvgId,rewriteTvgName,rewriteChannelName,rewritePlaylist,rewriteGroupInBlock,cleanUnmatchedChannel,getGroupFromBlock,hasPlaceholderTvgId,normalizeRules,getStreamUrlFromBlock,getPlayId,shouldConditionallyExclude,shouldRuleExcludeName,isHardExcludedName,versionedEpgUrl,normName};
