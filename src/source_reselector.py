from __future__ import annotations

import csv
import gzip
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .config import load_json, load_sources
from .metadata_enrichment import enrich_metadata
from .playlist import parse_m3u
from .utils import (
    convert_xmltv_timestamp,
    fetch_bytes,
    is_real_tvg_id,
    parse_xmltv_datetime,
    xmltv_programme_is_usable,
)
from .xmltv import XMLTVSource

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

DEFAULT_TARGET_HORIZON_HOURS = 6.0


def _enabled(value) -> bool:
    return str(value if value is not None else "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


def _read_policy(path: Path | None = None) -> list[dict]:
    path = path or DATA / "source_policy_v15.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if _enabled(r.get("enabled", "1"))]


def _source_name(source: dict, index: int) -> str:
    return source.get("name") or source.get("id") or f"source-{index}"


def _source_url(source: dict) -> str:
    return source.get("url") or source.get("xmltv") or source.get("epg_url") or ""


def _source_by_name() -> dict[str, dict]:
    return {
        _source_name(cfg, i): cfg
        for i, cfg in enumerate(load_sources())
        if cfg.get("enabled", True) is not False
    }


def _candidate_programmes(source: XMLTVSource, sid: str):
    programmes=[]
    now=datetime.now(timezone.utc)
    max_end=None
    current=False
    usable=0
    for p in source.fresh_programmes({sid}, past_days=1, future_days=21):
        start=parse_xmltv_datetime(p.get("start",""))
        stop=parse_xmltv_datetime(p.get("stop","")) or start
        if start is None:
            continue
        if xmltv_programme_is_usable(p.get("start",""), p.get("stop",""), now=now):
            usable += 1
        if stop is not None and (max_end is None or stop > max_end):
            max_end=stop
        if start <= now and (stop is None or stop >= now):
            current=True
        programmes.append(deepcopy(p))
    horizon = (
        (max_end-now).total_seconds()/3600.0
        if max_end is not None else -1e9
    )
    return programmes, horizon, current, usable


def choose_candidate(candidates: list[dict], target_hours: float = DEFAULT_TARGET_HORIZON_HOURS):
    """Choose a policy source after *all* allowed sources have been evaluated.

    candidates must already be in explicit policy order.

    Rule:
    1. Prefer the first policy candidate with enough future horizon.
    2. If none reaches the target, keep EPG by choosing the candidate with the
       longest still-positive horizon.
    3. Never choose a candidate with no usable/current-upcoming programme.
    """
    valid=[
        c for c in candidates
        if c.get("usable",0) > 0 and float(c.get("horizon_hours",-1e9)) > 0
    ]
    if not valid:
        return None

    for c in valid:
        if float(c["horizon_hours"]) >= target_hours:
            return c

    return max(valid, key=lambda c: float(c["horizon_hours"]))


def _download_policy_sources(policy_rows: list[dict]) -> dict[str, XMLTVSource]:
    configs=_source_by_name()
    wanted=[]
    for row in policy_rows:
        name=(row.get("source") or "").strip()
        if name and name not in wanted:
            wanted.append(name)

    loaded={}
    timeout_cap=max(5, int(os.environ.get("EPG_SOURCE_TIMEOUT_CAP","90") or 90))
    retries_cap=max(1, int(os.environ.get("EPG_SOURCE_RETRIES_CAP","2") or 2))

    for name in wanted:
        cfg=configs.get(name)
        if not cfg:
            print(f"[v15.1-selector] source not configured: {name}", flush=True)
            continue
        url=_source_url(cfg)
        if not url:
            continue
        try:
            cache_path=None
            if cfg.get("cache_fallback"):
                cache_path=ROOT/".cache"/"epg"/f"{name}.bin"
            data=fetch_bytes(
                url,
                timeout=min(int(cfg.get("timeout",180) or 180), timeout_cap),
                retries=min(int(cfg.get("retries",2) or 2), retries_cap),
                cache_bust_on_retry=bool(cfg.get("cache_bust_on_retry",False)),
                cache_path=cache_path,
                stale_if_error_seconds=int(cfg.get("stale_if_error_seconds",0) or 0),
            )
            loaded[name]=XMLTVSource(name,data).index()
            print(f"[v15.1-selector] loaded {name}", flush=True)
        except Exception as exc:
            print(f"[v15.1-selector] FAILED {name}: {exc}", flush=True)
    return loaded


def _load_mapping_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_mapping_rows(path: Path, rows: list[dict]):
    fields=[
        "playlist_name","playlist_tvg_id","output_tvg_id","group","region",
        "source","source_id","method","confidence"
    ]
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n",extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _load_playlist_names() -> dict[str, object]:
    url=os.environ.get("PLAYLIST_URL","").strip()
    if not url:
        return {}
    text=fetch_bytes(url,timeout=60,retries=2).decode("utf-8","replace")
    return {ch.name:ch for ch in parse_m3u(text)}


def _output_id(channel, policy_rows: list[dict], existing: dict | None):
    if existing and existing.get("output_tvg_id"):
        return existing["output_tvg_id"]
    tvg=(getattr(channel,"tvg_id","") or "").strip()
    if is_real_tvg_id(tvg):
        return tvg
    for row in policy_rows:
        sid=(row.get("source_id") or "").strip()
        if sid:
            return sid
    return ""


def _atomic_write_epg(path: Path, tv: ET.Element):
    fd,name=tempfile.mkstemp(prefix="epg-v151-",suffix=".xml.gz",dir=path.parent)
    os.close(fd)
    tmp=Path(name)
    try:
        with gzip.open(tmp,"wb",compresslevel=6) as gz:
            ET.ElementTree(tv).write(gz,encoding="utf-8",xml_declaration=True)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def reselect_policy_sources(target_hours: float | None = None) -> dict:
    """Re-evaluate every v15 policy chain against all allowed live sources.

    This phase runs after the generic builder but before publication QA. It
    corrects the generic builder's first-match-wins behavior for channels with
    an explicit source chain. The final XMLTV and mapping are rewritten from
    the chosen donor, so horizon QA audits the source that actually won.
    """
    target_hours=float(
        target_hours if target_hours is not None
        else os.environ.get("EPG_POLICY_TARGET_HOURS",DEFAULT_TARGET_HORIZON_HOURS)
    )
    policy=_read_policy()
    if not policy:
        return {"changed":0,"selected":0,"reason":"no-policy"}

    playlist=_load_playlist_names()
    by_channel=defaultdict(list)
    for row in policy:
        name=(row.get("playlist_name") or "").strip()
        if name and name in playlist:
            by_channel[name].append(row)

    if not by_channel:
        return {"changed":0,"selected":0,"reason":"no-policy-channels-in-playlist"}

    sources=_download_policy_sources(policy)
    mapping_path=OUTPUT/"mapping.csv"
    epg_path=OUTPUT/"epg.xml.gz"
    uhf_path=OUTPUT/"uhf-mapping.json"

    mapping_rows=_load_mapping_rows(mapping_path)
    mapping_by_name={r.get("playlist_name",""):r for r in mapping_rows}
    selected={}
    diagnostics=[]

    for channel_name, rows in by_channel.items():
        channel=playlist[channel_name]
        candidates=[]
        seen=set()
        for priority,row in enumerate(rows):
            source_name=(row.get("source") or "").strip()
            sid=(row.get("source_id") or "").strip()
            key=(source_name,sid)
            if not source_name or not sid or key in seen:
                continue
            seen.add(key)
            src=sources.get(source_name)
            if src is None or sid not in src.channels:
                diagnostics.append({
                    "playlist_name":channel_name,
                    "source":source_name,"source_id":sid,
                    "priority":priority,"status":"MISSING"
                })
                continue
            programmes,horizon,current,usable=_candidate_programmes(src,sid)
            c={
                "playlist_name":channel_name,
                "source":source_name,
                "source_id":sid,
                "priority":priority,
                "horizon_hours":horizon,
                "current":current,
                "usable":usable,
                "programmes":programmes,
                "source_obj":src,
            }
            candidates.append(c)
            diagnostics.append({
                "playlist_name":channel_name,
                "source":source_name,"source_id":sid,
                "priority":priority,
                "status":"CANDIDATE",
                "horizon_hours":round(horizon,2),
                "current":current,
                "usable":usable,
            })

        winner=choose_candidate(candidates,target_hours)
        if winner:
            winner["output_tvg_id"]=_output_id(
                channel,rows,mapping_by_name.get(channel_name)
            )
            if winner["output_tvg_id"]:
                selected[channel_name]=winner

    if not selected:
        (OUTPUT/"source-selection-v15.json").write_text(
            json.dumps({"target_hours":target_hours,"diagnostics":diagnostics},ensure_ascii=False,indent=2),
            encoding="utf-8"
        )
        return {"changed":0,"selected":0,"reason":"no-live-candidates"}

    with gzip.open(epg_path,"rb") as f:
        tv=ET.parse(f).getroot()

    selected_by_out=defaultdict(list)
    for name,w in selected.items():
        selected_by_out[w["output_tvg_id"]].append((name,w))

    # Remove the builder's first-match schedule only for output IDs we are
    # deterministically replacing. This prevents duplicate/contradictory NOW.
    for elem in list(tv):
        if elem.tag.split("}")[-1]=="programme" and elem.get("channel","") in selected_by_out:
            tv.remove(elem)

    existing_channel_ids={
        e.get("id","")
        for e in tv
        if e.tag.split("}")[-1]=="channel"
    }

    timezone_name=load_json("priorities.json").get("timezone","America/Los_Angeles")

    # One schedule per output id. HD/SD aliases that share an ID therefore do
    # not duplicate programmes.
    for out_id, items in selected_by_out.items():
        # All names sharing the output id should resolve to the same family.
        # If they differ, choose the strongest winner using the same rules.
        winners=[w for _,w in items]
        winner=choose_candidate(winners,target_hours) or winners[0]
        display_name=items[0][0]
        src=winner["source_obj"]
        sid=winner["source_id"]

        if out_id not in existing_channel_ids:
            ce=deepcopy(src.channels[sid])
            ce.set("id",out_id)
            dn=ET.Element("display-name")
            dn.text=display_name
            ce.insert(0,dn)
            tv.insert(0,ce)
            existing_channel_ids.add(out_id)

        for programme in winner["programmes"]:
            p=deepcopy(programme)
            p.set("channel",out_id)
            for attr in ("start","stop"):
                if p.get(attr):
                    p.set(attr,convert_xmltv_timestamp(p.get(attr),timezone_name))
            tv.append(p)

    # Replace mapping rows for selected playlist names.
    selected_names=set(selected)
    mapping_rows=[r for r in mapping_rows if r.get("playlist_name") not in selected_names]
    for name,w in selected.items():
        ch=playlist[name]
        mapping_rows.append({
            "playlist_name":name,
            "playlist_tvg_id":getattr(ch,"tvg_id","") or "",
            "output_tvg_id":w["output_tvg_id"],
            "group":getattr(ch,"group","") or "",
            "region":"",
            "source":w["source"],
            "source_id":w["source_id"],
            "method":"policy-best-source",
            "confidence":"100",
        })
    _write_mapping_rows(mapping_path,mapping_rows)

    # Re-apply local SQLite metadata to newly inserted programmes.
    old_env={k:os.environ.get(k) for k in (
        "METADATA_MAX_TITLES","METADATA_MAX_HTTP_REQUESTS","METADATA_MULTI_FALLBACK"
    )}
    try:
        os.environ["METADATA_MAX_TITLES"]="0"
        os.environ["METADATA_MAX_HTTP_REQUESTS"]="0"
        os.environ["METADATA_MULTI_FALLBACK"]="0"
        enrich_metadata(tv,mapping_rows,ROOT,OUTPUT)
    finally:
        for k,v in old_env.items():
            if v is None:
                os.environ.pop(k,None)
            else:
                os.environ[k]=v

    _atomic_write_epg(epg_path,tv)

    if uhf_path.exists():
        payload=json.loads(uhf_path.read_text(encoding="utf-8"))
    else:
        payload={"channels":{}}
    channels_map=dict(payload.get("channels",{}))
    for name,w in selected.items():
        channels_map[name]=w["output_tvg_id"]
    payload["channels"]=channels_map
    payload["source_selection_v15"]={
        name:{
            "source":w["source"],
            "source_id":w["source_id"],
            "horizon_hours":round(float(w["horizon_hours"]),2),
        }
        for name,w in selected.items()
    }
    uhf_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    report={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "target_hours":target_hours,
        "selected":{
            name:{
                "source":w["source"],
                "source_id":w["source_id"],
                "output_tvg_id":w["output_tvg_id"],
                "horizon_hours":round(float(w["horizon_hours"]),2),
                "current":bool(w["current"]),
                "usable":int(w["usable"]),
            }
            for name,w in selected.items()
        },
        "diagnostics":diagnostics,
    }
    (OUTPUT/"source-selection-v15.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"
    )

    for src in sources.values():
        try:
            src.release()
        except Exception:
            pass

    print(
        f"[v15.1-selector] selected={len(selected)} target={target_hours:g}h",
        flush=True,
    )
    for name,w in selected.items():
        print(
            f"[v15.1-selector] {name}: {w['source']} / {w['source_id']} "
            f"horizon={w['horizon_hours']:.2f}h",
            flush=True,
        )

    return {"changed":len(selected),"selected":len(selected),"target_hours":target_hours}
