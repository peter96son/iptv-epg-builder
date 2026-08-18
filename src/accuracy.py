from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .region import is_regional_sensitive, regions_compatible

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Country suffixes used by many XMLTV providers.  The check is deliberately
# conservative: only explicit suffixes/tokens are interpreted as a country.
COUNTRY_PATTERNS = {
    "RU": (r"(?:^|[._-])ru(?:$|[._-])",),
    "UA": (r"(?:^|[._-])ua(?:$|[._-])", r"(?:^|[._-])ukr(?:$|[._-])"),
    "IL": (r"(?:^|[._-])il(?:$|[._-])",),
    "PL": (r"(?:^|[._-])pl(?:$|[._-])",),
    "RO": (r"(?:^|[._-])ro(?:$|[._-])",),
    "BG": (r"(?:^|[._-])bg(?:$|[._-])",),
    "DE": (r"(?:^|[._-])de(?:$|[._-])",),
    "GB": (r"(?:^|[._-])gb(?:$|[._-])", r"(?:^|[._-])uk(?:$|[._-])"),
    "US": (r"(?:^|[._-])us(?:$|[._-])", r"(?:^|[._-])usa(?:$|[._-])"),
    "CA": (r"(?:^|[._-])ca(?:$|[._-])",),
    "IT": (r"(?:^|[._-])it(?:$|[._-])",),
    "GR": (r"(?:^|[._-])gr(?:$|[._-])",),
    "TR": (r"(?:^|[._-])tr(?:$|[._-])",),
    "PT": (r"(?:^|[._-])pt(?:$|[._-])",),
    "HR": (r"(?:^|[._-])hr(?:$|[._-])",),
    "HU": (r"(?:^|[._-])hu(?:$|[._-])",),
    "CZ": (r"(?:^|[._-])cz(?:$|[._-])",),
    "SK": (r"(?:^|[._-])sk(?:$|[._-])",),
    "LT": (r"(?:^|[._-])lt(?:$|[._-])",),
    "LV": (r"(?:^|[._-])lv(?:$|[._-])",),
    "MD": (r"(?:^|[._-])md(?:$|[._-])",),
}

COMPOSITE_ALLOWED = {
    "BE/NL": {"BE", "NL", "BE/NL"},
    "CZ/SK": {"CZ", "SK", "CZ/SK"},
}


def infer_id_region(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    hits = []
    for region, patterns in COUNTRY_PATTERNS.items():
        if any(re.search(pattern, text, re.I) for pattern in patterns):
            hits.append(region)
    return hits[0] if len(hits) == 1 else ""


def load_accuracy_overrides(path: Path | None = None) -> dict[tuple[str, str], dict]:
    path = path or (DATA / "accuracy_overrides.csv")
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("enabled", "1")).strip().lower() in {"0", "false", "no", "off"}:
                continue
            name = (row.get("playlist_name") or "").strip()
            source_id = (row.get("source_id") or "").strip()
            if name:
                out[(name, source_id)] = {k: (v or "").strip() for k, v in row.items()}
                if not source_id:
                    out[(name, "*")] = out[(name, source_id)]
    return out


def _override_for(row: dict, overrides: dict) -> dict | None:
    key = (row.get("playlist_name", ""), row.get("source_id", ""))
    return overrides.get(key) or overrides.get((row.get("playlist_name", ""), "*"))


def assess_mapping(row: dict, source_cfg: dict | None = None, overrides: dict | None = None) -> dict:
    """Classify one mapping for publication safety.

    `wrong` is quarantined automatically. `verified`, `probable` and
    `unverified` remain publishable, but are visible in the audit report.
    """
    source_cfg = source_cfg or {}
    overrides = overrides or {}
    override = _override_for(row, overrides)
    if override:
        status = (override.get("status") or "unverified").lower()
        return {
            "accuracy_status": status,
            "accuracy_reason": override.get("reason", "manual accuracy override"),
            "evidence_url": override.get("evidence_url", ""),
            "quarantine": status == "wrong",
        }

    method = (row.get("method") or "").strip()
    source = (row.get("source") or "").strip()
    name = (row.get("playlist_name") or "").strip()
    region = (row.get("region") or "").strip().upper()
    sid = (row.get("source_id") or "").strip()
    out_id = (row.get("output_tvg_id") or "").strip()
    confidence = int(row.get("confidence") or 0)

    if method.startswith("synthetic") or source.endswith("local-fallback"):
        return {
            "accuracy_status": "wrong",
            "accuracy_reason": "synthetic schedule is not a verified real broadcast schedule",
            "evidence_url": "",
            "quarantine": True,
        }

    id_region = infer_id_region(sid) or infer_id_region(out_id)
    if region and id_region:
        allowed = COMPOSITE_ALLOWED.get(region, {region})
        if id_region not in allowed:
            return {
                "accuracy_status": "wrong",
                "accuracy_reason": f"explicit XMLTV country {id_region} conflicts with provider region {region}",
                "evidence_url": "",
                "quarantine": True,
            }

    source_regions = source_cfg.get("regions") or source_cfg.get("region_scope") or []
    if region and is_regional_sensitive(name) and source_regions:
        if not regions_compatible(region, source_regions):
            return {
                "accuracy_status": "wrong",
                "accuracy_reason": "regional-sensitive brand matched from an incompatible country feed",
                "evidence_url": "",
                "quarantine": True,
            }

    # Manual aliases are researched mappings; exact IDs are strong but can
    # still be wrong in provider metadata, so only aliases are called verified.
    if method == "alias":
        status = "verified"
        reason = "researched exact alias"
    elif method in {"id", "name-region"} and confidence >= 96:
        status = "probable"
        reason = "strong exact match; no country conflict detected"
    else:
        status = "unverified"
        reason = "mapping has not yet been cross-checked against an independent schedule"

    return {
        "accuracy_status": status,
        "accuracy_reason": reason,
        "evidence_url": "",
        "quarantine": False,
    }


def build_accuracy_audit(mappings: list[dict], source_cfg_by_name: dict[str, dict], overrides: dict | None = None):
    overrides = overrides or {}
    rows = []
    quarantine = []
    counts = defaultdict(int)
    for row in mappings:
        result = assess_mapping(row, source_cfg_by_name.get(row.get("source", ""), {}), overrides)
        audit = {
            "playlist_name": row.get("playlist_name", ""),
            "playlist_tvg_id": row.get("playlist_tvg_id", ""),
            "output_tvg_id": row.get("output_tvg_id", ""),
            "group": row.get("group", ""),
            "region": row.get("region", ""),
            "source": row.get("source", ""),
            "source_id": row.get("source_id", ""),
            "method": row.get("method", ""),
            "confidence": row.get("confidence", 0),
            **result,
        }
        rows.append(audit)
        counts[result["accuracy_status"]] += 1
        if result["quarantine"]:
            quarantine.append(audit)
    return rows, quarantine, dict(counts)
