# IPTV EPG Builder v12.0

`Update EPG` is now a complete automatic pipeline.

Sequence:
1. download/build the current programme;
2. use the existing SQLite knowledge base immediately;
3. run a 5000-request backfill on the just-built current EPG;
4. store newly found metadata in SQLite;
5. reopen the same current `output/epg.xml.gz`;
6. apply the updated SQLite genres/descriptions/IMDb metadata locally;
7. save `data/metadata.sqlite3.gz`;
8. commit the final enriched EPG.

Backfill and finalization do not redownload the XMLTV source fleet. The initial
build uses zero new TMDb HTTP requests; all metadata network work is concentrated
in the prioritized backfill stage.

The separate Backfill workflow remains available manually, but Update EPG no
longer depends on a second run before new metadata appears on the TV.
