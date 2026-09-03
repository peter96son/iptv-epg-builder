v15.13 — OCR results become real EPG.
Hourly Verify Missing Movie EPG now consumes high/medium recognized titles,
updates persistent live-ocr-epg-state.json, injects current XMLTV programmes
into epg.xml.gz, updates uhf-mapping.json, reruns movie EPG audit, and commits
the real EPG outputs. Normal Update EPG reapplies still-fresh OCR state after
the regular build so OCR channels survive the 3-hour rebuild.
