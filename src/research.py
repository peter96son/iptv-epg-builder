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


RUSSIAN_CIS_TOPIC_GROUPS = {
    "Россия", "Беларусь", "Украинские", "Кино", "Кино 4K", "Кинозалы", "Кинозалы UA",
    "Музыкальные", "Познавательные", "Детские", "Новости", "Спорт", "Разное",
}

# Explicit virtual/FAST families are kept visible in the report but marked unsafe
# for automatic alias recovery. This prevents a Russian title from being mistaken
# for a conventional linear TV channel with the same programme/film name.
RUSSIAN_CIS_UNSAFE_FAMILIES = {"DITV", "VeleS", "Magic", "KLI", "Play-X", "BCU", "Joker", "Clarity", "CPS", "NEXT", "CineMan", "MiniMax/MM", "Fresh", "BOX", "Velilla", "KBC"}


def russian_cis_candidate(row: dict) -> tuple[bool, str]:
    name = (row.get("playlist_name") or "").strip()
    group = (row.get("group") or "").strip()
    region = (row.get("region") or "").strip()
    if not name:
        return False, ""

    if region in {"RU", "BY"} or group in {"Россия", "Беларусь"}:
        return True, "provider-region"

    # Russian-language channels are also placed by IPTV.online into topical groups.
    # Ukrainian-specific letters are a useful conservative signal to avoid treating
    # clearly Ukrainian titles as Russian-language recovery candidates.
    has_cyrillic = bool(re.search(r"[А-Яа-яЁё]", name))
    has_ukrainian_specific = bool(re.search(r"[ІіЇїЄєҐґ]", name))
    if group in RUSSIAN_CIS_TOPIC_GROUPS and has_cyrillic and not has_ukrainian_specific:
        return True, "cyrillic-topical-group"

    return False, ""


def build_russian_cis_unmatched_reports(unmatched: list[dict], output_dir: Path) -> dict:
    rows = []
    for row in unmatched:
        include, reason = russian_cis_candidate(row)
        if not include:
            continue
        family = classify_family(row.get("playlist_name", ""))
        unsafe = family in RUSSIAN_CIS_UNSAFE_FAMILIES or (row.get("playlist_tvg_id") or "").lower().startswith("no_epg")
        rows.append({
            "playlist_name": row.get("playlist_name", ""),
            "playlist_tvg_id": row.get("playlist_tvg_id", ""),
            "group": row.get("group", ""),
            "region": row.get("region", ""),
            "family": family,
            "candidate_reason": reason,
            "automatic_recovery_allowed": "no" if unsafe else "review",
        })

    rows.sort(key=lambda r: (r["automatic_recovery_allowed"], r["group"].lower(), r["playlist_name"].lower()))
    group_counts = Counter((r["group"] or "(без категории)") for r in rows)
    family_counts = Counter(r["family"] for r in rows)
    payload = {
        "candidate_channels": len(rows),
        "requires_manual_or_dedicated_epg": sum(1 for r in rows if r["automatic_recovery_allowed"] == "no"),
        "groups": dict(group_counts.most_common()),
        "families": dict(family_counts.most_common()),
        "channels": rows,
    }
    save_json(output_dir / "unmatched-russian-cis.json", payload)
    write_csv(
        output_dir / "unmatched-russian-cis.csv", rows,
        ["playlist_name", "playlist_tvg_id", "group", "region", "family", "candidate_reason", "automatic_recovery_allowed"],
    )
    md = [
        "# Russian/CIS unmatched recovery queue", "",
        "Diagnostic queue for Russian-language and CIS recovery. It does not create aliases by itself.",
        "Regional variants, time-shifts and virtual/FAST families must be verified before production mapping.", "",
        f"Candidate channels: **{len(rows)}**", "",
        f"Unsafe virtual/dummy-ID channels: **{payload['requires_manual_or_dedicated_epg']}**", "",
        "## By group", "",
    ]
    for group, count in group_counts.most_common():
        md.append(f"- {group}: {count}")
    md.extend(["", "## Channels", "", "| Channel | Group | Region | Family | Recovery |", "|---|---|---|---|---|"])
    for r in rows:
        md.append(f"| {r['playlist_name']} | {r['group']} | {r['region']} | {r['family']} | {r['automatic_recovery_allowed']} |")
    (output_dir / "unmatched-russian-cis.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return payload
