from types import SimpleNamespace
from pathlib import Path
import csv

import src.v15_policy_patch as v15
from src.config import load_aliases
from src.matcher import Matcher

class S:
    def __init__(self,name,channels=None,names=None):
        self.name=name
        self.channels=channels or {}
        self.names=names or {}

def ch(name,tvg_id="",group="Кино"):
    return SimpleNamespace(name=name,tvg_id=tvg_id,tvg_name=name,group=group)

def test_hard_pin_cannot_be_bypassed_by_unlisted_rescue_source():
    aliases=[
        {"enabled":"1","playlist_name":"X","source":"dedicated","source_id":"x","hard_pin":"1"},
        {"enabled":"1","playlist_name":"X","source":"fallback","source_id":"x","hard_pin":"0"},
    ]
    m=Matcher(aliases)
    assert m._source_allowed(ch("X"),S("dedicated"),{"rescue_source":False})
    assert m._source_allowed(ch("X"),S("fallback"),{"rescue_source":True})
    assert not m._source_allowed(ch("X"),S("random-rescue"),{"rescue_source":True})

def test_unlisted_rescue_cannot_match_even_if_id_exists():
    aliases=[
        {"enabled":"1","playlist_name":"X","source":"dedicated","source_id":"x","hard_pin":"1"},
        {"enabled":"1","playlist_name":"X","source":"fallback","source_id":"x","hard_pin":"0"},
    ]
    m=Matcher(aliases)
    c=ch("X","x")
    sid,method,confidence=m.match(c,S("random-rescue",{"x":object()}),{"rescue_source":True},allow_family=False)
    assert sid is None and method is None and confidence == 0

def test_v15_policy_contains_verified_4ever_and_premiere_chains():
    rows=load_aliases()
    by_name={}
    for r in rows:
        by_name.setdefault(r.get("playlist_name",""),set()).add((r.get("source",""),r.get("source_id","")))
    assert ("iptvx-noarch","4ever-cinema") in by_name["4ever Cinema HD"]
    assert ("openbox-tsd","4ever-cinema") in by_name["4ever Cinema HD"]
    assert ("gabbarit-current","4 ever Cinema") in by_name["4ever Cinema HD"]
    assert ("premiere-group-dedicated","premium-hd") in by_name["Premium HD"]
    assert ("gabbarit-current","USSR HD") in by_name["USSR HD"]

def test_4ever_music_does_not_invent_unverified_gabbarit_donor():
    rows=load_aliases()
    music=[r for r in rows if r.get("playlist_name") in {"4ever Music","4ever Music HD"}]
    # Existing historical source_pins may contain IPTVX/Openbox; v15 adds no
    # fabricated Gabbarit Music source.
    v15_rows=[]
    p=Path(__file__).resolve().parents[1]/"data"/"source_policy_v15.csv"
    with p.open(encoding="utf-8-sig",newline="") as f:
        v15_rows=list(csv.DictReader(f))
    assert not any(
        r["playlist_name"] in {"4ever Music","4ever Music HD"} and r["source"].startswith("gabbarit")
        for r in v15_rows
    )

def test_duplicate_physical_source_canonicalization():
    assert v15._canonical_source_url("http://gabbarit.drm-play.com/epg_1.xml.gz") == \
           v15._canonical_source_url("https://gabbarit.drm-play.com/epg_1.xml.gz")
    assert v15._canonical_source_url("https://www.teleguide.info/download/new3/xmltv.xml.gz") == \
           v15._canonical_source_url("https://teleguide.info/download/new3/xmltv.xml.gz")

def test_source_policy_csv_schema_is_stable():
    p=Path(__file__).resolve().parents[1]/"data"/"source_policy_v15.csv"
    with p.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.reader(f))
    assert rows[0] == ["enabled","playlist_name","playlist_tvg_id","provider_group","region","source","source_id","hard_pin","notes"]
    assert all(len(r)==9 for r in rows)


def test_duplicate_merge_preserves_union_of_group_scopes(monkeypatch):
    physical="http://gabbarit.drm-play.com/epg_1.xml.gz"
    monkeypatch.setattr(v15,"_ORIGINAL_LOAD_SOURCES",lambda:[
        {"name":"gabbarit-current","url":physical,"groups":["Кино"],"timeout":100},
        {"name":"gabbarit-primary","url":physical.replace("http://","https://"),
         "groups":["Кино","USSR"],"timeout":300,"cache_fallback":True,"rescue_source":True},
    ])
    rows=v15.load_sources_v15()
    assert len(rows)==1
    row=rows[0]
    assert row["name"]=="gabbarit-current"
    assert {"Кино","USSR"} <= set(row["groups"])
    assert row["timeout"]==300
    assert row["cache_fallback"] is True


def test_ussr_gabbarit_fallback_survives_dedup_scope_merge(monkeypatch):
    physical="http://gabbarit.drm-play.com/epg_1.xml.gz"
    monkeypatch.setattr(v15,"_ORIGINAL_LOAD_SOURCES",lambda:[
        {"name":"gabbarit-current","url":physical,"groups":["Кино"]},
        {"name":"gabbarit-primary","url":physical,"groups":["Кино","USSR"],"rescue_source":True},
    ])
    rows=v15.load_sources_v15()
    assert rows[0]["name"]=="gabbarit-current"
    assert "USSR" in rows[0]["groups"]
