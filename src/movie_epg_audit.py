from __future__ import annotations
import csv, gzip, json, os, re, urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

from .playlist import ATTR, parse_m3u

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
GROUPS = {"Кино", "USSR", "Кинозалы", "Кино 4K"}

def _fetch_text(url: str) -> str:
    req=urllib.request.Request(url,headers={"User-Agent":"iptv-movie-qa/13.23"})
    import time
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except (TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise last_error

def _parse_ts(value: str):
    m=re.match(r"(\d{12,14})(?:\s*([+-]\d{4}))?", value or "")
    if not m:
        return None
    raw=m.group(1)
    fmt="%Y%m%d%H%M%S" if len(raw)==14 else "%Y%m%d%H%M"
    try:
        d=datetime.strptime(raw,fmt)
    except ValueError:
        return None
    off=m.group(2)
    if off:
        sign=1 if off[0]=="+" else -1
        mins=sign*(int(off[1:3])*60+int(off[3:5]))
        d=d.replace(tzinfo=timezone(timedelta(minutes=mins)))
    else:
        d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def _rules():
    try:
        return json.loads((DATA/"playlist_rules.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

def _provider_catchup_info(playlist_text: str, channel) -> tuple[str, str]:
    """Return non-sensitive catch-up mode/day settings from global or channel tags."""
    header = next((line for line in playlist_text.splitlines() if line.strip().startswith("#EXTM3U")), "")
    global_tags = dict(ATTR.findall(header))
    channel_tags = dict(ATTR.findall(getattr(channel, "extinf", "")))
    mode = channel_tags.get("catchup", global_tags.get("catchup", ""))
    days = channel_tags.get("catchup-days", global_tags.get("catchup-days", ""))
    mode = str(mode or "").strip()
    days = str(days or "").strip()
    if days and not days.isdigit():
        days = ""
    return mode, days

def run(strict: bool=False):
    playlist_url=os.environ.get("PLAYLIST_URL","").strip()
    if not playlist_url:
        raise SystemExit("movie QA: PLAYLIST_URL is missing")
    playlist_text=_fetch_text(playlist_url)
    raw_channels=parse_m3u(playlist_text)
    rules=_rules()
    excluded=set(rules.get("exclude_groups",[]) or [])
    group_overrides=rules.get("group_overrides",{}) or {}
    name_overrides=rules.get("name_overrides",{}) or {}

    mapping_payload=json.loads((OUTPUT/"uhf-mapping.json").read_text(encoding="utf-8"))
    mapping=mapping_payload.get("channels",{})

    with gzip.open(OUTPUT/"epg.xml.gz","rb") as f:
        root=ET.parse(f).getroot()
    epg_ids={c.get("id","") for c in root.findall("channel")}
    programmes={}
    for p in root.findall("programme"):
        programmes.setdefault(p.get("channel",""),[]).append(p)

    now=datetime.now(timezone.utc)
    rows=[]
    for ch in raw_channels:
        original_group=ch.group
        if original_group in excluded:
            continue
        final_group=group_overrides.get(ch.name, original_group)
        if final_group not in GROUPS:
            continue
        final_name=name_overrides.get(ch.name,ch.name)
        catchup_mode,catchup_days=_provider_catchup_info(playlist_text,ch)
        cid=str(mapping.get(ch.name,"") or "")
        arr=programmes.get(cid,[]) if cid else []
        current=[]; future=[]; max_stop=None; future_7day_count=0
        for p in arr:
            st=_parse_ts(p.get("start","")); en=_parse_ts(p.get("stop",""))
            if st and en and st <= now < en:
                current.append(p)
            if st and st > now:
                future.append(p)
                if st <= now + timedelta(days=7):
                    future_7day_count += 1
            if en and (max_stop is None or en>max_stop):
                max_stop=en
        horizon_hours=(max_stop-now).total_seconds()/3600 if max_stop else None
        live_ocr_current=any(p.get("x-live-ocr")=="1" for p in current)
        issues=[]
        if not cid:
            issues.append("NO_MAPPING")
        elif cid not in epg_ids:
            issues.append("ID_NOT_IN_EPG")
        elif not arr:
            issues.append("NO_PROGRAMMES")
        elif not current:
            issues.append("NO_CURRENT_PROGRAMME")
        if cid and arr and not future and not live_ocr_current:
            issues.append("NO_NEXT_PROGRAMME")
        rows.append({
            "group":final_group,
            "playlist_name":final_name,
            "provider_name":ch.name,
            "provider_tvg_id":ch.tvg_id,
            "provider_catchup_mode":catchup_mode,
            "provider_catchup_days":catchup_days,
            "output_tvg_id":cid,
            "programme_count":len(arr),
            "current_count":len(current),
            "future_count":len(future),
            "future_7day_count":future_7day_count,
            "future_horizon_hours":"" if horizon_hours is None else round(horizon_hours,2),
            "seven_day_coverage":bool(horizon_hours is not None and horizon_hours>=168),
            "current_mode":"LIVE_OCR" if live_ocr_current else ("EPG" if current else ""),
            "status":"OK" if not issues else ";".join(issues),
        })

    gaps=[r for r in rows if r["status"]!="OK"]
    fields=["group","playlist_name","provider_name","provider_tvg_id","provider_catchup_mode","provider_catchup_days","output_tvg_id",
            "programme_count","current_count","future_count","future_7day_count",
            "future_horizon_hours","seven_day_coverage","current_mode","status"]
    for fn,data in (("movie-epg-audit.csv",rows),("movie-epg-gaps.csv",gaps)):
        with (OUTPUT/fn).open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)

    summary={
        "checked_at_utc":now.isoformat(),
        "groups":sorted(GROUPS),
        "channels":len(rows),
        "ok":len(rows)-len(gaps),
        "gaps":len(gaps),
        "issue_counts":dict(Counter(
            issue for r in gaps for issue in r["status"].split(";")
        )),
        "group_counts":{
            g:{
                "channels":sum(r["group"]==g for r in rows),
                "ok":sum(r["group"]==g and r["status"]=="OK" for r in rows),
                "gaps":sum(r["group"]==g and r["status"]!="OK" for r in rows),
                "seven_day":sum(r["group"]==g and r["seven_day_coverage"] for r in rows),
            } for g in sorted(GROUPS)
        },
        "seven_day_channels":sum(r["seven_day_coverage"] for r in rows),
        "under_seven_day_channels":sum(not r["seven_day_coverage"] for r in rows),
        "provider_archive_days_counts":dict(Counter(r["provider_catchup_days"] for r in rows if r["provider_catchup_days"])),
        "channels_advertising_seven_day_archive":sum(int(r["provider_catchup_days"] or 0)>=7 for r in rows),
    }
    (OUTPUT/"movie-epg-audit.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

    if strict and gaps:
        preview=", ".join(r["playlist_name"] for r in gaps[:12])
        raise SystemExit(
            f"MOVIE EPG QA FAILED: {len(gaps)} gaps remain in movie groups. "
            f"Nothing should be published. First gaps: {preview}. "
            f"See output/movie-epg-gaps.csv"
        )
    return summary

if __name__=="__main__":
    run(strict=False)
