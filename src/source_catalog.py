from __future__ import annotations

import json
from datetime import datetime, timezone

from .source_reselector import _download_policy_sources, _read_policy

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def _display_names(channel_elem) -> list[str]:
    names=[]
    for elem in channel_elem:
        if elem.tag.split("}")[-1] == "display-name" and elem.text:
            value=elem.text.strip()
            if value and value not in names:
                names.append(value)
    return names


def _terms_from_missing(missing_rows: list[dict]) -> set[str]:
    terms={"premium","premiere","ussr","paradise","paradox","spg","4ever","4 ever"}
    for row in missing_rows:
        for key in ("playlist_name","source_id"):
            value=(row.get(key) or "").strip().lower()
            if not value:
                continue
            terms.add(value)
            for token in value.replace("-"," ").replace("_"," ").split():
                if len(token) >= 4:
                    terms.add(token)
    return terms


def snapshot_missing_source_catalog() -> dict:
    """Persist actual XMLTV IDs/names for sources involved in missing policy rows.

    The selector already writes output/source-selection-v15.json. We use its
    MISSING rows to decide which source feeds need a catalog snapshot, so this
    diagnostic pass does not redownload unrelated IPTVX/Openbox feeds.

    No stream URLs or raw XMLTV payloads are written.
    """
    selection_path=OUTPUT/"source-selection-v15.json"
    if not selection_path.exists():
        return {"sources":0,"channels":0,"reason":"no-selection-report"}

    selection=json.loads(selection_path.read_text(encoding="utf-8"))
    missing=[
        row for row in selection.get("diagnostics",[])
        if row.get("status")=="MISSING"
    ]
    if not missing:
        payload={
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "sources":{},
            "missing_policy_rows":[],
        }
        (OUTPUT/"source-catalog-v15.json").write_text(
            json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"
        )
        return {"sources":0,"channels":0,"reason":"no-missing-policy-rows"}

    source_names=[]
    for row in missing:
        name=(row.get("source") or "").strip()
        if name and name not in source_names:
            source_names.append(name)

    all_policy=_read_policy()
    minimal_policy=[
        row for row in all_policy
        if (row.get("source") or "").strip() in source_names
    ]
    sources=_download_policy_sources(minimal_policy)
    terms=_terms_from_missing(missing)

    out={}
    total=0
    for source_name,src in sources.items():
        rows=[]
        horizons=getattr(src,"horizon_hours_by_id",{}) or {}
        for cid,elem in src.channels.items():
            names=_display_names(elem)
            haystack=" ".join([cid,*names]).lower()
            if not any(term in haystack for term in terms):
                continue
            h=horizons.get(cid)
            rows.append({
                "id":cid,
                "display_names":names,
                "horizon_hours":None if h is None else round(float(h),2),
            })
        rows.sort(key=lambda r:(
            (r["display_names"][0] if r["display_names"] else r["id"]).lower(),
            r["id"].lower()
        ))
        out[source_name]={
            "matching_count":len(rows),
            "indexed_usable_channels":len(src.channels),
            "matching_channels":rows,
        }
        total += len(rows)

    payload={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "purpose":"Actual channel IDs/display names from live EPG feeds for missing v15 policy rows",
        "sources":out,
        "missing_policy_rows":missing,
    }
    (OUTPUT/"source-catalog-v15.json").write_text(
        json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"
    )

    for src in sources.values():
        try:
            src.release()
        except Exception:
            pass

    print(
        f"[source-catalog] sources={len(out)} matching_channels={total}",
        flush=True,
    )
    return {"sources":len(out),"channels":total}
