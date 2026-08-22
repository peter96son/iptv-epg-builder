import assert from "node:assert/strict";
import { rewritePlaylist } from "./worker.js";
const sample=`#EXTM3U catchup="flussonic" tvg-rec="5" timeshift="5"
#EXTINF:-1 tvg-id="a",CPS USSR
#EXTGRP:Кинозалы
http://example/cps
#EXTINF:-1 tvg-id="b",MM USSR Драма HD
#EXTGRP:Кино
http://example/mm
#EXTINF:-1 tvg-id="c",UA Movie
#EXTGRP:Кино UA
http://example/ua`;
const r=rewritePlaylist(sample,{},"https://example/epg.gz",{exclude_groups:["Кино UA"],group_overrides:{"CPS USSR":"USSR","MM USSR Драма HD":"USSR"}});
assert.equal(r.excluded,1); assert.equal(r.regrouped,2);
assert.match(r.playlist,/#EXTGRP:USSR/); assert.doesNotMatch(r.playlist,/UA Movie/);
assert.match(r.playlist,/catchup="flussonic"/); assert.match(r.playlist,/tvg-rec="5"/); assert.match(r.playlist,/timeshift="5"/);
console.log("worker personalization tests passed");
