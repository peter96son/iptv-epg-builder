from datetime import datetime,timezone
import src.live_epg_verifier as v

def test_title_similarity():
    assert v._similarity("Горько!", "ГОРЬКО") >= 0.9
    assert v._similarity("12 стульев (1971)", "12 стульев") >= 0.9
    assert v._similarity("Игра", "Бегущий в лабиринте") < v.MATCH_THRESHOLD

def test_two_mismatches_required():
    state={"cursor":0,"channels":{}}
    now=datetime(2026,9,3,12,0,tzinfo=timezone.utc)
    row={"provider_name":"VHS HD","verdict":"MISMATCH","epg_title":"Игра","ocr_title":"Дерево Джошуа","similarity":0.1,"ocr_confidence":"high"}
    v._apply_observation(state,row,now)
    assert state["channels"]["VHS HD"]["status"]=="MISMATCH_PENDING"
    v._apply_observation(state,dict(row),now)
    assert state["channels"]["VHS HD"]["status"]=="MISMATCH_CONFIRMED"

def test_verified_resets_streak():
    state={"cursor":0,"channels":{"X":{"mismatch_streak":2,"status":"MISMATCH_CONFIRMED"}}}
    now=datetime(2026,9,3,12,0,tzinfo=timezone.utc)
    row={"provider_name":"X","verdict":"VERIFIED","epg_title":"ИГРА","ocr_title":"ИГРА"}
    v._apply_observation(state,row,now)
    assert state["channels"]["X"]["mismatch_streak"]==0
    assert state["channels"]["X"]["status"]=="VERIFIED"
