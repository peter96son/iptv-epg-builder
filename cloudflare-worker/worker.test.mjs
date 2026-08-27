import test from "node:test";
import assert from "node:assert/strict";
import {rewritePlaylist,versionedEpgUrl} from "./worker.js";

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

test("Serial Ukraine is removed by current user policy",()=>{
 const src=`#EXTM3U
#EXTINF:-1,Серіал Україна 1
#EXTGRP:Кино
http://bel.seetv.cc/play/1667/SECRET/video.m3u8`;
 const r=rewritePlaylist(src,{},"https://x/epg",{group_overrides:{"Серіал Україна 1":"Сериалы"}});
 assert.doesNotMatch(r.playlist,/Серіал Україна 1/);
 assert.equal(r.excluded,1);
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


test("Fresh TV Armenia stays Music and both category fields are rewritten",()=>{
 const src=`#EXTM3U
#EXTINF:-1 group-title="Кино",Fresh TV Armenia
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{group_overrides:{"Fresh TV Armenia":"Музыкальные"}});
 assert.match(r.playlist,/group-title="Музыкальные"/);
 assert.match(r.playlist,/#EXTGRP:Музыкальные/);
});

test("Viasat True Crime CEE stays Educational",()=>{
 const src=`#EXTM3U
#EXTINF:-1 group-title="Кино",Viasat True Crime CEE
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{group_overrides:{"Viasat True Crime CEE":"Познавательные"}});
 assert.match(r.playlist,/group-title="Познавательные"/);
 assert.match(r.playlist,/#EXTGRP:Познавательные/);
});

test("Russian serial word automatically moves channel to Series",()=>{
 const src=`#EXTM3U
#EXTINF:-1 group-title="Кино",НТВ Сериал Невский
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{});
 assert.match(r.playlist,/group-title="Сериалы"/);
 assert.match(r.playlist,/#EXTGRP:Сериалы/);
});

test("English serial word automatically moves channel to Series",()=>{
 const src=`#EXTM3U
#EXTINF:-1 group-title="Кино",BOX Serial HD
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{});
 assert.match(r.playlist,/group-title="Сериалы"/);
});

test("Cine+ is still removed after cumulative fixes",()=>{
 const src=`#EXTM3U
#EXTINF:-1 group-title="Кино",Cine+ Legend
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{},"https://x/epg",{exclude_name_prefixes:["Cine+"]});
 assert.doesNotMatch(r.playlist,/Cine\\+/);
});


test("hard blacklist removes Ukrainian cinema feeds even when rules JSON is empty",()=>{
 const src=`#EXTM3U
#EXTINF:-1 group-title="Кино",Cine+ HD
#EXTGRP:Кино
http://a
#EXTINF:-1 group-title="Кино",Cine+ Legend
#EXTGRP:Кино
http://b
#EXTINF:-1 group-title="Кино",Твоє Кіно Хіт
#EXTGRP:Кино
http://c
#EXTINF:-1 group-title="Кино",Твое кино Action
#EXTGRP:Кино
http://d
#EXTINF:-1 group-title="Кино",PROKINO
#EXTGRP:Кино
http://e
#EXTINF:-1 group-title="Кино",1+1 Кіно
#EXTGRP:Кино
http://f`;
 const r=rewritePlaylist(src,{},"https://x/epg",{});
 assert.doesNotMatch(r.playlist,/Cine\+|Твоє Кіно|Твое кино|PROKINO|1\+1 Кіно/i);
 assert.equal(r.excluded,6);
});


test("normalized mapping supplies exact tvg-id and tvg-name for strict players",()=>{
 const src=`#EXTM3U
#EXTINF:-1 tvg-name="wrong upstream name" group-title="Кино",KINO PREMIERE GROUP HD
#EXTGRP:Кино
http://a`;
 const r=rewritePlaylist(src,{"Kino Premiere Group HD":"epg.strict.id"},"https://x/epg.xml.gz",{});
 assert.match(r.playlist,/tvg-id="epg.strict.id"/);
 assert.match(r.playlist,/tvg-name="KINO PREMIERE GROUP HD"/);
});

test("versioned EPG URL changes when a new mapping build is published",()=>{
 const u=versionedEpgUrl("https://example.com/epg.xml.gz","2026-08-25T20:53:20-07:00");
 assert.equal(u.startsWith("https://example.com/epg.xml.gz?v="),true);
});


test("v14.11 removes requested Ukrainian-only non-sports channels but keeps Ukrainian sports",()=>{
 const removed=[
  "Star Cinema HD","Star Cinema","M1 HD","M2 HD","MusicBox UA HD","UA.Music HD",
  "Серіал Україна 1","Серіал Україна 2","FilmUA Drama","Про Київ","EWTN Украина"
 ];
 const sports=["Sport 1 UA","Суспільне Спорт","Setanta Sports Ukraine"];
 const blocks=[...removed,...sports].map((name,i)=>`#EXTINF:-1 group-title="${sports.includes(name)?"Спорт":"Разное"}",${name}\n#EXTGRP:${sports.includes(name)?"Спорт":"Разное"}\nhttp://example/${i}`).join("\n");
 const r=rewritePlaylist(`#EXTM3U\n${blocks}`,{},"https://x/epg",{});
 for(const name of removed) assert.equal(r.playlist.includes(name),false,`must remove ${name}`);
 for(const name of sports) assert.equal(r.playlist.includes(name),true,`must keep sports ${name}`);
});
