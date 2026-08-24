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
