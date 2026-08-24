import test from "node:test";
import assert from "node:assert/strict";
import {rewritePlaylist} from "./worker.js";

test("name override happens after mapping lookup and preserves EPG mapping",()=>{
 const src=`#EXTM3U
#EXTINF:-1 tvg-id="" tvg-name="BCU_UTIFY_2_HD",BCU_UTIFY_2_HD
#EXTGRP:Кинозалы
http://a`;
 const r=rewritePlaylist(src,{"BCU_UTIFY_2_HD":"bcu-catastrophe"},"https://x/epg",{
   name_overrides:{"BCU_UTIFY_2_HD":"BCU Catastrophe HD"}
 });
 assert.match(r.playlist,/tvg-id="bcu-catastrophe"/);
 assert.match(r.playlist,/tvg-name="BCU Catastrophe HD"/);
 assert.match(r.playlist,/,BCU Catastrophe HD/);
 assert.equal(r.renamed,1);
});

test("Utify 1 can get Comedy EPG without being renamed",()=>{
 const src=`#EXTM3U
#EXTINF:-1 tvg-id="",BCU_UTIFY_1_HDR
#EXTGRP:Кинозалы
http://a`;
 const r=rewritePlaylist(src,{"BCU_UTIFY_1_HDR":"bcu-comedy"},"https://x/epg",{});
 assert.match(r.playlist,/tvg-id="bcu-comedy"/);
 assert.match(r.playlist,/,BCU_UTIFY_1_HDR/);
});

test("Ukrainian movie channel is hidden only for matching name plus provider play id",()=>{
 const yes=`#EXTM3U
#EXTINF:-1,Cine+ HD
#EXTGRP:Кино
http://bel.seetv.cc/play/7996/SECRET/video.m3u8`;
 const r1=rewritePlaylist(yes,{},"https://x/epg",{});
 assert.doesNotMatch(r1.playlist,/,Cine\+ HD/);
 assert.equal(r1.conditionalExcluded,1);

 const repurposed=`#EXTM3U
#EXTINF:-1,Other Movie HD
#EXTGRP:Кино
http://bel.seetv.cc/play/7996/SECRET/video.m3u8`;
 const r2=rewritePlaylist(repurposed,{},"https://x/epg",{});
 assert.match(r2.playlist,/,Other Movie HD/);

 const moved=`#EXTM3U
#EXTINF:-1,Cine+ HD
#EXTGRP:Кино
http://bel.seetv.cc/play/9999/SECRET/video.m3u8`;
 const r3=rewritePlaylist(moved,{},"https://x/epg",{});
 assert.match(r3.playlist,/,Cine\+ HD/);
});


test("playlist header advertises EPG using both url-tvg and x-tvg-url",()=>{
 const src=`#EXTM3U catchup="flussonic"
#EXTINF:-1,CPS Drama
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{"CPS Drama":"cps-drama"},"https://x/epg",{});
 const header=r.playlist.split("\n")[0];
 assert.match(header,/url-tvg="https:\/\/x\/epg"/);
 assert.match(header,/x-tvg-url="https:\/\/x\/epg"/);
});

test("existing EPG header attributes are both replaced",()=>{
 const src=`#EXTM3U url-tvg="old1" x-tvg-url="old2"
#EXTINF:-1,CPS Action
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{"CPS Action":"cps-action"},"https://new/epg",{});
 const header=r.playlist.split("\n")[0];
 assert.equal((header.match(/url-tvg=/g)||[]).length,1);
 assert.equal((header.match(/x-tvg-url=/g)||[]).length,1);
 assert.match(header,/url-tvg="https:\/\/new\/epg"/);
 assert.match(header,/x-tvg-url="https:\/\/new\/epg"/);
});
