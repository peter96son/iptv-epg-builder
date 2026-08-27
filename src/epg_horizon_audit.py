"""Final build guard against publishing EPG mappings that are about to expire.

This is the second line of defence after horizon_guard_patch. The source-level
guard lets later providers win; this final audit verifies the merged output that
UHF will actually receive.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from .utils import parse_xmltv_datetime

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def audit(epg_path=None, mapping_path=None, *, now=None, min_hours=None):
    epg_path = Path(epg_path or OUTPUT / "epg.xml.gz")
    mapping_path = Path(mapping_path or OUTPUT / "uhf-mapping.json")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    min_hours = float(min_hours if min_hours is not None else os.environ.get("EPG_PUBLISH_MIN_FUTURE_HOURS", "6"))

    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    channel_map = payload.get("channels", {})
    wanted = set(channel_map.values())
    max_stop = {}
    counts = {}

    opener = gzip.open if epg_path.suffix == ".gz" else open
    with opener(epg_path, "rb") as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag.split("}")[-1] != "programme":
                continue
            cid = elem.get("channel", "")
            if cid in wanted:
                stop = parse_xmltv_datetime(elem.get("stop", "")) or parse_xmltv_datetime(elem.get("start", ""))
                if stop is not None:
                    if cid not in max_stop or stop > max_stop[cid]:
                        max_stop[cid] = stop
                    counts[cid] = counts.get(cid, 0) + 1
            elem.clear()

    rows=[]
    bad_ids=set()
    for name, cid in channel_map.items():
        end=max_stop.get(cid)
        horizon=(end-now).total_seconds()/3600 if end else None
        if end is None:
            status="NO_PROGRAMMES"
            bad_ids.add(cid)
        elif horizon < 0:
            status="STALE"
            bad_ids.add(cid)
        elif horizon < min_hours:
            status="EXPIRING_SOON"
            bad_ids.add(cid)
        else:
            status="OK"
        rows.append({
            "playlist_name":name,
            "tvg_id":cid,
            "status":status,
            "future_horizon_hours":"" if horizon is None else round(horizon,2),
            "last_programme_utc":"" if end is None else end.isoformat(),
            "programme_count":counts.get(cid,0),
        })

    summary={
        "generated_at":now.isoformat(),
        "minimum_publish_future_hours":min_hours,
        "mapped_channels":len(channel_map),
        "unique_mapped_ids":len(wanted),
        "bad_unique_ids":len(bad_ids),
        "bad_channel_rows":sum(r["status"] != "OK" for r in rows),
    }
    return summary, rows


def main():
    summary, rows = audit()
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "epg-horizon-audit.json").write_text(json.dumps({"summary":summary,"channels":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUTPUT / "epg-horizon-audit.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["playlist_name","tvg_id","status","future_horizon_hours","last_programme_utc","programme_count"])
        w.writeheader(); w.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if summary["bad_unique_ids"]:
        raise SystemExit(1)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
