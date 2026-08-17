from __future__ import annotations
from dataclasses import asdict

def snapshot_channels(channels):
    return [
        {
            "name": c.name,
            "tvg_id": c.tvg_id,
            "tvg_name": c.tvg_name,
            "group": c.group,
            "stream_url": c.stream_url,
        }
        for c in channels
    ]

def _key(item):
    # Prefer tvg_id when useful, otherwise exact name.
    return (item.get("tvg_id") or "").strip() or item.get("name", "").strip()

def compare_snapshots(previous: list[dict], current: list[dict]) -> dict:
    prev = {_key(x): x for x in previous if _key(x)}
    curr = {_key(x): x for x in current if _key(x)}

    added_keys = [k for k in curr if k not in prev]
    removed_keys = [k for k in prev if k not in curr]

    changed_streams = []
    changed_groups = []
    renamed = []

    for k in curr.keys() & prev.keys():
        a = prev[k]
        b = curr[k]
        if a.get("stream_url") != b.get("stream_url"):
            changed_streams.append({
                "key": k,
                "name": b.get("name", ""),
                "old": a.get("stream_url", ""),
                "new": b.get("stream_url", ""),
            })
        if a.get("group") != b.get("group"):
            changed_groups.append({
                "key": k,
                "name": b.get("name", ""),
                "old": a.get("group", ""),
                "new": b.get("group", ""),
            })
        if a.get("name") != b.get("name"):
            renamed.append({
                "key": k,
                "old": a.get("name", ""),
                "new": b.get("name", ""),
            })

    return {
        "added_count": len(added_keys),
        "removed_count": len(removed_keys),
        "renamed_count": len(renamed),
        "stream_url_changed_count": len(changed_streams),
        "group_changed_count": len(changed_groups),
        "added": [curr[k] for k in added_keys],
        "removed": [prev[k] for k in removed_keys],
        "renamed": renamed,
        "stream_url_changed": changed_streams,
        "group_changed": changed_groups,
    }
