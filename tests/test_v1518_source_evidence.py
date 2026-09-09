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
