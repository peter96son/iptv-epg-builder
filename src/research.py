from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from .reports import write_csv
from .state import save_json

# Known virtual/FAST/cinema families that should be researched as a unit.
# This module is diagnostic only: it NEVER creates live EPG mappings.
FAMILY_RULES = [
    ("DITV", re.compile(r"^DITV(?:\s|$)", re.I)),
    ("VeleS", re.compile(r"^VeleS(?:\s|$)", re.I)),
    ("Magic", re.compile(r"^Magic(?:\s|$)", re.I)),
    ("KLI", re.compile(r"^(?:KLI|KLI\s*MEDIA)(?:\s|$)", re.I)),
    ("Play-X", re.compile(r"^(?:Play[- ]?X)(?:\s|$)", re.I)),
    ("BCU", re.compile(r"^(?:BCU|BCU\s*Media)(?:\s|$)", re.I)),
    ("Joker", re.compile(r"^(?:Joker(?::|\s|$)|jk[_-])", re.I)),
    ("Clarity", re.compile(r"^Clarity(?:4K)?(?:\s|$)", re.I)),
    ("CPS", re.compile(r"^CPS(?:\s|$)", re.I)),
    ("NEXT", re.compile(r"^NEXT(?:\s|$)", re.I)),
    ("CineMan", re.compile(r"^CineMan(?:\s|$)", re.I)),
    ("MiniMax/MM", re.compile(r"^(?:MiniMax|MM)(?:\s|$)", re.I)),
    ("Fresh", re.compile(r"^Fresh(?:\s|$)", re.I)),
    ("BOX", re.compile(r"^BOX(?:\s|$)", re.I)),
    ("Velilla", re.compile(r"^Velilla(?:\s|$)", re.I)),
    ("KBC", re.compile(r"^KBC(?:\s|$)", re.I)),
]

GENERIC_PREFIXES = {
    "hd", "fhd", "uhd", "4k", "tv", "channel", "канал", "кино", "movie",
    "cinema", "the", "русский", "россия", "украина", "ua", "ru", "us", "uk",
}


def classify_family(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "(empty-name)"

    for family, rule in FAMILY_RULES:
        if rule.search(name):
            return family

    # Stable automatic bucket for newly discovered families. This is only a report
    # grouping and is never used as an EPG match.
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9+_-]+", name)
    if not tokens:
        return "Other"

    first = tokens[0]
    if first.lower() in GENERIC_PREFIXES and len(tokens) > 1:
        first = tokens[1]

    if len(first) <= 1 or first.isdigit():
        return "Other"

    return f"Other: {first}"


def build_unmatched_family_reports(unmatched: list[dict], output_dir: Path) -> dict:
    rows = []
    by_family = defaultdict(list)

    for row in unmatched:
        family = classify_family(row.get("playlist_name", ""))
        item = {
            "family": family,
            "playlist_name": row.get("playlist_name", ""),
            "playlist_tvg_id": row.get("playlist_tvg_id", ""),
            "group": row.get("group", ""),
            "region": row.get("region", ""),
        }
        rows.append(item)
        by_family[family].append(item)

    rows.sort(key=lambda r: (r["family"].lower(), r["group"].lower(), r["playlist_name"].lower()))

    summary = []
    for family, items in by_family.items():
        groups = Counter((i.get("group") or "(без категории)") for i in items)
        dummy_ids = sum(1 for i in items if (i.get("playlist_tvg_id") or "").lower().startswith("no_epg"))
        summary.append({
            "family": family,
            "channels": len(items),
            "dummy_no_epg_ids": dummy_ids,
            "groups": dict(groups.most_common()),
            "channels_list": [i["playlist_name"] for i in items],
        })

    summary.sort(key=lambda x: (-x["channels"], x["family"].lower()))

    payload = {
        "unmatched_channels": len(unmatched),
        "families": summary,
    }
    save_json(output_dir / "unmatched-families.json", payload)
    write_csv(
        output_dir / "unmatched-families.csv",
        rows,
        ["family", "playlist_name", "playlist_tvg_id", "group", "region"],
    )

    md = [
        "# Unmatched channel families",
        "",
        "This report is diagnostic only. It does not create EPG mappings.",
        "A family must be researched and verified before aliases are added to the live builder.",
        "",
        f"Unmatched channels: **{len(unmatched)}**",
        "",
        "| Family | Channels | no_epg_* IDs | Main groups |",
        "|---|---:|---:|---|",
    ]
    for item in summary:
        groups_text = ", ".join(f"{g} ({n})" for g, n in list(item["groups"].items())[:4])
        md.append(
            f"| {item['family']} | {item['channels']} | {item['dummy_no_epg_ids']} | {groups_text} |"
        )

    md.extend(["", "## Channels by family", ""])
    for item in summary:
        md.append(f"### {item['family']} — {item['channels']}")
        md.append("")
        for channel_name in item["channels_list"]:
            md.append(f"- {channel_name}")
        md.append("")

    (output_dir / "unmatched-families.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return payload
