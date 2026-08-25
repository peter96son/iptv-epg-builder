import test from "node:test";
import assert from "node:assert/strict";
import {rewritePlaylist} from "./worker.js";

test("Cine+ family is removed unconditionally by v14 rules",()=>{
 const src=`#EXTM3U
#EXTINF:-1,Cine+ Hit HD
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{exclude_name_prefixes:["Cine+"]});
 assert.doesNotMatch(r.playlist,/Cine\+/);
 assert.equal(r.excluded,1);
});

test("PROKINO and Ukrainian Tvoie Kino are removed by name policy",()=>{
 const src=`#EXTM3U
#EXTINF:-1,PROKINO
#EXTGRP:Кино
http://a
#EXTINF:-1,Твоє Кіно Хіт
#EXTGRP:Кино
http://b`;
 const r=rewritePlaylist(src,{},"https://x/epg",{exclude_name_prefixes:["PROKINO","Твоє Кіно"]});
 assert.doesNotMatch(r.playlist,/PROKINO|Твоє Кіно/);
 assert.equal(r.excluded,2);
});

test("Serial Ukraine is kept and moved to Series",()=>{
 const src=`#EXTM3U
#EXTINF:-1,Серіал Україна 1
#EXTGRP:Кино
http://bel.seetv.cc/play/1667/SECRET/video.m3u8`;
 const r=rewritePlaylist(src,{},"https://x/epg",{group_overrides:{"Серіал Україна 1":"Сериалы"}});
 assert.match(r.playlist,/Серіал Україна 1/);
 assert.match(r.playlist,/#EXTGRP:Сериалы/);
 assert.equal(r.conditionalExcluded,0);
});

test("case-insensitive group override works",()=>{
 const src=`#EXTM3U
#EXTINF:-1,AMEDIA HIT
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{group_overrides:{"Amedia Hit":"Сериалы"}});
 assert.match(r.playlist,/#EXTGRP:Сериалы/);
});

test("name override preserves EPG mapping",()=>{
 const src=`#EXTM3U
#EXTINF:-1 tvg-id="",BCU_UTIFY_2_HD
#EXTGRP:Кинозалы
http://a`;
 const r=rewritePlaylist(src,{"BCU_UTIFY_2_HD":"bcu-catastrophe"},"https://x/epg",{name_overrides:{"BCU_UTIFY_2_HD":"BCU Catastrophe HD"}});
 assert.match(r.playlist,/tvg-id="bcu-catastrophe"/);
 assert.match(r.playlist,/,BCU Catastrophe HD/);
});
