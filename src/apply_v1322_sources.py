from pathlib import Path
import json
p=Path("data/sources.json")
data=json.loads(p.read_text(encoding="utf-8"))
found=False
for s in data:
    if s.get("name")=="iptv-online-primary":
        s["url"]="https://iptv.online/epg/epg.xml.gz"
        s["note"]="Provider primary EPG. Keep first; incomplete coverage is supplemented by fallbacks."
        found=True
if not found:
    data.insert(0,{"name":"iptv-online-primary","url":"https://iptv.online/epg/epg.xml.gz","enabled":True,"timeout":180})
p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
