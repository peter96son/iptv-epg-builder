from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import src.source_evidence as ev

def _p(title, start, stop):
    p=ET.Element("programme",start=start.strftime("%Y%m%d%H%M%S +0000"),stop=stop.strftime("%Y%m%d%H%M%S +0000"))
    ET.SubElement(p,"title").text=title
    return p

def test_title_similarity_handles_year_and_punctuation():
    assert ev._similar("Адвокат дьявола (1997)","Адвокат дьявола") >= .95

def test_programme_at_uses_timestamp():
    t=datetime(2026,9,5,2,10,tzinfo=timezone.utc)
    p=_p("Адвокат дьявола",t-timedelta(minutes=30),t+timedelta(minutes=30))
    assert ev._programme_at([p],t) is p

def test_install_appends_evidence_candidates(monkeypatch,tmp_path):
    cand=tmp_path/"c.csv"
    cand.write_text("enabled,playlist_name,source,source_id,notes\n1,BCU VHS HD,a,b,x\n",encoding="utf-8")
    monkeypatch.setattr(ev,"CANDIDATE_PATH",cand)
    mod=SimpleNamespace(_read_policy=lambda path=None: [],choose_candidate=lambda c,target_hours=6.0: c[0] if c else None)
    monkeypatch.setattr(ev,"_INSTALLED",False)
    ev.install(mod)
    rows=mod._read_policy()
    assert rows[0]["playlist_name"]=="BCU VHS HD"
    assert rows[0]["source"]=="a"

def test_evidence_beats_policy_order_and_longer_horizon(monkeypatch, tmp_path):
    t = datetime(2026, 9, 5, 2, 10, tzinfo=timezone.utc)
    obs = tmp_path / "obs.csv"
    obs.write_text(
        "enabled,playlist_name,observed_at,observed_title,notes\n"
        f"1,BCU VHS HD,{t.isoformat()},Адвокат дьявола,test\n",
        encoding="utf-8",
    )
    state = tmp_path / "state.json"
    monkeypatch.setattr(ev, "OBS_PATH", obs)
    monkeypatch.setattr(ev, "STATE_PATH", state)
    monkeypatch.setattr(ev, "_INSTALLED", False)

    mod = SimpleNamespace(
        _read_policy=lambda path=None: [],
        choose_candidate=lambda c, target_hours=6.0: c[0] if c else None,
    )
    ev.install(mod)

    candidates = [
        {
            "playlist_name": "BCU VHS HD",
            "source": "wrong-first",
            "source_id": "wrong",
            "priority": 0,
            "usable": 20,
            "horizon_hours": 240.0,
            "programmes": [
                _p("Водный мир", t-timedelta(hours=1), t+timedelta(hours=1))
            ],
        },
        {
            "playlist_name": "BCU VHS HD",
            "source": "verified-second",
            "source_id": "right",
            "priority": 1,
            "usable": 2,
            "horizon_hours": 8.0,
            "programmes": [
                _p(
                    "Адвокат дьявола (1997)",
                    t-timedelta(hours=1),
                    t+timedelta(hours=1),
                )
            ],
        },
    ]

    winner = mod.choose_candidate(candidates, 6.0)
    assert winner["source"] == "verified-second"
    assert winner["_evidence_negative"] == 0


def test_contradictory_observation_blocks_learned_winner(monkeypatch, tmp_path):
    import json

    t = datetime(2026, 9, 5, 2, 10, tzinfo=timezone.utc)
    obs = tmp_path / "obs.csv"
    obs.write_text(
        "enabled,playlist_name,observed_at,observed_title,notes\n"
        f"1,BCU VHS HD,{t.isoformat()},Адвокат дьявола,test\n",
        encoding="utf-8",
    )
    state = tmp_path / "state.json"
    state.write_text(
        '{"channels":{"BCU VHS HD":{"source":"old","source_id":"old-id"}}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(ev, "OBS_PATH", obs)
    monkeypatch.setattr(ev, "STATE_PATH", state)
    monkeypatch.setattr(ev, "_INSTALLED", False)

    mod = SimpleNamespace(
        _read_policy=lambda path=None: [],
        choose_candidate=lambda c, target_hours=6.0: c[0] if c else None,
    )
    ev.install(mod)

    candidates = [{
        "playlist_name": "BCU VHS HD",
        "source": "old",
        "source_id": "old-id",
        "priority": 0,
        "usable": 20,
        "horizon_hours": 240.0,
        "programmes": [
            _p("Водный мир", t-timedelta(hours=1), t+timedelta(hours=1))
        ],
    }]

    assert mod.choose_candidate(candidates, 6.0) is None
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["channels"]["BCU VHS HD"]["status"] == "conflict"

