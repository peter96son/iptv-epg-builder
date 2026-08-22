from __future__ import annotations

import argparse
import gzip
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .title_normalization_patch import normalize_existing_compact_title

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EPG = ROOT / "output" / "epg.xml.gz"
DEFAULT_RULES = ROOT / "data" / "metadata_overrides.json"

GENERATED_TITLE_SUFFIX_RE = re.compile(
    r"\s*\(\s*(?:19|20)\d{2}\s*\)\s*(?:[·•]\s*IMDb\s*[0-9]+(?:[.,][0-9]+)?\s*)?$",
    re.I,
)
PREFIX_RE = re.compile(
    r"^\s*(?:х/ф|м/ф|т/с|д/с|д/ф|сериал|фильм|кино)\s*[:.\-–—]?\s*",
    re.I,
)


def _base_title(value: str) -> str:
    text = (value or "").strip()
    text = GENERATED_TITLE_SUFFIX_RE.sub("", text).strip()
    text = PREFIX_RE.sub("", text).strip()
    return re.sub(r"\s+", " ", text).strip(" -–—:;,.")


def _parse_xmltv(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def _duration_minutes(programme: ET.Element) -> int | None:
    start = _parse_xmltv(programme.get("start", ""))
    stop = _parse_xmltv(programme.get("stop", ""))
    if not start or not stop:
        return None
    return max(0, int((stop - start).total_seconds() // 60))


def _channel_names(root: ET.Element) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for channel in root.findall("channel"):
        cid = (channel.get("id") or "").strip()
        out[cid] = [
            (node.text or "").strip()
            for node in channel.findall("display-name")
            if (node.text or "").strip()
        ]
    return out


def _matches(rule: dict, programme: ET.Element, names: list[str]) -> bool:
    if not rule.get("enabled", True):
        return False
    title = programme.findtext("title") or ""
    if _base_title(title).casefold() != str(rule.get("title_base") or "").strip().casefold():
        return False

    minimum = int(rule.get("min_duration_minutes") or 0)
    if minimum:
        duration = _duration_minutes(programme)
        if duration is None or duration < minimum:
            return False

    needles = [
        str(x or "").casefold()
        for x in (rule.get("channel_name_contains_any") or [])
        if str(x or "").strip()
    ]
    if needles:
        haystack = " | ".join(names).casefold()
        if not any(needle in haystack for needle in needles):
            return False
    return True


def _set_text(programme: ET.Element, tag: str, value: str) -> None:
    node = programme.find(tag)
    if node is None:
        node = ET.SubElement(programme, tag)
    node.text = value


def _remove_imdb_metadata(programme: ET.Element) -> None:
    for rating in list(programme.findall("rating")):
        if (rating.get("system") or "").strip().casefold() == "imdb":
            programme.remove(rating)
    for url in list(programme.findall("url")):
        if "imdb.com/title/" in (url.text or "").casefold():
            programme.remove(url)


def _apply_rule(programme: ET.Element, rule: dict) -> None:
    year = str(rule.get("year") or "").strip()
    rating = str(rule.get("imdb_rating") or "").strip()
    imdb_id = str(rule.get("imdb_id") or "").strip()
    base = str(rule.get("title_base") or "").strip()

    title = base
    if year:
        title += f" ({year})"
    if rating:
        title += f" · IMDb {rating}"
    _set_text(programme, "title", title)

    if year:
        _set_text(programme, "date", year)
    if rule.get("description"):
        _set_text(programme, "desc", str(rule["description"]))

    _remove_imdb_metadata(programme)

    if rating:
        rating_node = ET.SubElement(programme, "rating", {"system": "IMDb"})
        ET.SubElement(rating_node, "value").text = f"{rating}/10"
    if imdb_id:
        ET.SubElement(programme, "url").text = f"https://www.imdb.com/title/{imdb_id}/"

    existing_categories = {
        (node.text or "").strip().casefold()
        for node in programme.findall("category")
        if (node.text or "").strip()
    }
    for genre in rule.get("genres") or []:
        genre = str(genre or "").strip()
        if genre and genre.casefold() not in existing_categories:
            ET.SubElement(programme, "category", {"lang": "ru"}).text = genre
            existing_categories.add(genre.casefold())


def apply_verified_metadata_fixes(
    epg_path: str | Path = DEFAULT_EPG,
    rules_path: str | Path = DEFAULT_RULES,
) -> dict:
    epg_path = Path(epg_path)
    rules_path = Path(rules_path)

    if not epg_path.exists():
        return {"ok": False, "reason": "epg_missing", "changed": 0}

    rules = []
    if rules_path.exists():
        payload = json.loads(rules_path.read_text(encoding="utf-8"))
        rules = [r for r in payload.get("rules", []) if isinstance(r, dict)]

    with gzip.open(epg_path, "rb") as fh:
        root = ET.parse(fh).getroot()

    names_by_id = _channel_names(root)
    rule_changes = 0
    normalized_titles = 0
    matches: list[dict] = []

    # First apply verified manual corrections.
    for programme in root.findall("programme"):
        cid = (programme.get("channel") or "").strip()
        names = names_by_id.get(cid, [])
        for rule in rules:
            if not _matches(rule, programme, names):
                continue
            old_title = programme.findtext("title") or ""
            _apply_rule(programme, rule)
            new_title = programme.findtext("title") or ""
            rule_changes += 1
            matches.append({
                "rule": rule.get("id", ""),
                "channel": cid,
                "channel_names": names,
                "start": programme.get("start", ""),
                "old_title": old_title,
                "new_title": new_title,
                "duration_minutes": _duration_minutes(programme),
            })
            break

    # Then make all generated compact titles idempotent, including merged history.
    title_examples = []
    for programme in root.findall("programme"):
        title_node = programme.find("title")
        if title_node is None:
            continue
        old = (title_node.text or "").strip()
        new = normalize_existing_compact_title(old)
        if new and new != old:
            title_node.text = new
            normalized_titles += 1
            if len(title_examples) < 25:
                title_examples.append({"old": old, "new": new})

    changed = rule_changes + normalized_titles
    if changed:
        tmp = epg_path.with_suffix(epg_path.suffix + ".tmp")
        with gzip.open(tmp, "wb", compresslevel=6) as fh:
            ET.ElementTree(root).write(fh, encoding="utf-8", xml_declaration=True)
        tmp.replace(epg_path)

    report = {
        "ok": True,
        "changed": changed,
        "rule_changes": rule_changes,
        "normalized_titles": normalized_titles,
        "rules": len(rules),
        "matches": matches,
        "title_normalization_examples": title_examples,
    }
    report_path = ROOT / "output" / "verified-metadata-fixes.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("epg", nargs="?", default=str(DEFAULT_EPG))
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    args = parser.parse_args()
    result = apply_verified_metadata_fixes(args.epg, args.rules)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
