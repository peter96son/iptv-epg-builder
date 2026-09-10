from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from .utils import parse_xmltv_datetime

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE_PATH = DATA / "source_evidence_state.json"
OBS_PATH = DATA / "live_epg_observations_v1518.csv"
CANDIDATE_PATH = DATA / "live_source_candidates_v1518.csv"

_INSTALLED = False


def _enabled(value) -> bool:
    return str(value if value is not None else "1").strip().lower() not in {
        "0", "false", "no", "off"
    }


def _norm(value: str) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    s = s.replace("ё", "е")
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)
    s = re.sub(r"[^0-9a-zа-я]+", " ", s, flags=re.I)
    return " ".join(s.split())


def _similar(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        if shorter >= 6 and shorter / max(longer, 1) >= 0.70:
            return 0.95
    return SequenceMatcher(None, a, b).ratio()


def _title(programme) -> str:
    for child in list(programme):
        if child.tag.split("}")[-1] == "title" and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def _parse_iso(value: str):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _programme_at(programmes, when):
    for p in programmes or []:
        start = parse_xmltv_datetime(p.get("start", ""))
        stop = parse_xmltv_datetime(p.get("stop", "")) or start
        if start is None:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        else:
            start = start.astimezone(timezone.utc)
        if stop is not None:
            if stop.tzinfo is None:
                stop = stop.replace(tzinfo=timezone.utc)
            else:
                stop = stop.astimezone(timezone.utc)
        if start <= when and (stop is None or when < stop):
            return p
    return None


def _read_rows(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if _enabled(r.get("enabled", "1"))]


def _observations_for(channel_name: str):
    rows = []
    for row in _read_rows(OBS_PATH):
        if (row.get("playlist_name") or "").strip() != channel_name:
            continue
        dt = _parse_iso(row.get("observed_at"))
        title = (row.get("observed_title") or "").strip()
        if dt and title:
            row = dict(row)
            row["_dt"] = dt
            rows.append(row)
    return rows


def _load_state():
    if not STATE_PATH.exists():
        return {"channels": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"channels": {}}
    except Exception:
        return {"channels": {}}


def _save_state(state):
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _candidate_evidence(candidate: dict, observations: list[dict]):
    matches = []
    for obs in observations:
        p = _programme_at(candidate.get("programmes", []), obs["_dt"])
        if p is None:
            continue
        actual = _title(p)
        score = _similar(actual, obs.get("observed_title", ""))
        matches.append({
            "observed_at": obs.get("observed_at"),
            "observed_title": obs.get("observed_title"),
            "candidate_title": actual,
            "similarity": round(score, 4),
            "matched": score >= 0.82,
        })
    positive = sum(1 for m in matches if m["matched"])
    negative = sum(1 for m in matches if not m["matched"])
    return positive, negative, matches


def _load_extra_policy():
    rows = []
    for row in _read_rows(CANDIDATE_PATH):
        rows.append({
            "enabled": "1",
            "playlist_name": (row.get("playlist_name") or "").strip(),
            "source": (row.get("source") or "").strip(),
            "source_id": (row.get("source_id") or "").strip(),
            "hard_pin": "0",
            "evidence_required": "1",
            "notes": (row.get("notes") or "live evidence candidate").strip(),
        })
    return [r for r in rows if r["playlist_name"] and r["source"] and r["source_id"]]


def install(source_reselector_module):
    """Install evidence-aware policy selection for v15.18.

    The existing source selector remains the fallback. Live/manual evidence only
    overrides it when a candidate schedule actually matches a timestamped
    observation. A learned winner remains preferred on later runs while usable;
    a new contradictory observation can replace it.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original_read_policy = source_reselector_module._read_policy
    original_choose = source_reselector_module.choose_candidate

    def read_policy(path=None):
        base = list(original_read_policy(path))
        if path is not None:
            return base
        seen = {
            (
                (r.get("playlist_name") or "").strip(),
                (r.get("source") or "").strip(),
                (r.get("source_id") or "").strip(),
            )
            for r in base
        }
        for row in _load_extra_policy():
            key = (row["playlist_name"], row["source"], row["source_id"])
            if key not in seen:
                base.append(row)
                seen.add(key)
        return base

    def choose(candidates, target_hours=6.0):
        valid = [
            c for c in candidates
            if c.get("usable", 0) > 0 and float(c.get("horizon_hours", -1e9)) > 0
        ]
        if not valid:
            return original_choose(candidates, target_hours)

        channel_name = (valid[0].get("playlist_name") or "").strip()
        observations = _observations_for(channel_name) if channel_name else []
        state = _load_state()
        channels = state.setdefault("channels", {})

        if observations:
            ranked = []
            for c in valid:
                pos, neg, detail = _candidate_evidence(c, observations)
                c["_evidence_positive"] = pos
                c["_evidence_negative"] = neg
                c["_evidence_detail"] = detail
                ranked.append(c)

            clean = [c for c in ranked if c["_evidence_negative"] == 0]
            eligible = [
                c for c in clean
                if c["_evidence_positive"] >= int(c.get("min_evidence", 1) or 1)
            ]
            best_positive = max(
                (c["_evidence_positive"] for c in eligible),
                default=0,
            )
            if best_positive > 0:
                winners = [
                    c for c in eligible
                    if c["_evidence_positive"] == best_positive
                ]
                winner = max(
                    winners,
                    key=lambda c: (
                        float(c.get("horizon_hours", 0)),
                        -int(c.get("priority", 999999)),
                    ),
                )
                channels[channel_name] = {
                    "source": winner.get("source"),
                    "source_id": winner.get("source_id"),
                    "positive_observations": int(winner["_evidence_positive"]),
                    "negative_observations": 0,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "evidence": winner.get("_evidence_detail", []),
                }
                _save_state(state)
                winner["_evidence_selected"] = True
                return winner

            learned = channels.get(channel_name)
            if isinstance(learned, dict):
                learned_candidate = next(
                    (
                        c for c in ranked
                        if c.get("source") == learned.get("source")
                        and c.get("source_id") == learned.get("source_id")
                    ),
                    None,
                )
                if (
                    learned_candidate is not None
                    and learned_candidate.get("_evidence_negative", 0) > 0
                ):
                    channels[channel_name] = {
                        **learned,
                        "status": "conflict",
                        "conflict_at": datetime.now(timezone.utc).isoformat(),
                        "evidence": learned_candidate.get("_evidence_detail", []),
                    }
                    _save_state(state)
            return None

        learned = channels.get(channel_name) if channel_name else None
        if isinstance(learned, dict) and learned.get("status") != "conflict":
            for c in valid:
                if (
                    c.get("source") == learned.get("source")
                    and c.get("source_id") == learned.get("source_id")
                ):
                    c["_evidence_selected"] = True
                    return c

        if any(_enabled(c.get("evidence_required", "0")) for c in valid):
            return None

        return original_choose(candidates, target_hours)

    source_reselector_module._read_policy = read_policy
    source_reselector_module.choose_candidate = choose
    _INSTALLED = True
