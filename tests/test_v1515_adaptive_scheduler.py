from datetime import datetime,timezone,timedelta
import src.live_epg_verifier as v
def _row(name):return {"provider_name":name,"playlist_name":name,"group":"Кино","output_tvg_id":"id-"+name}
def test_trusted_after_confirmations():
    state={"channels":{}};now=datetime(2026,9,3,12,0,tzinfo=timezone.utc)
    row={"provider_name":"A","group":"Кино","output_tvg_id":"x","verdict":"VERIFIED","epg_title":"ИГРА","ocr_title":"ИГРА"}
    for _ in range(v.TRUST_AFTER):v._apply_observation(state,dict(row),now)
    assert state["channels"]["A"]["status"]=="TRUSTED"
def test_no_onscreen_title_after_repeated_empty_ocr():
    state={"channels":{}};now=datetime(2026,9,3,12,0,tzinfo=timezone.utc)
    row={"provider_name":"B","group":"Кино","output_tvg_id":"y","verdict":"NO_CONFIDENT_OCR"}
    for _ in range(v.NO_TITLE_AFTER):v._apply_observation(state,dict(row),now)
    assert state["channels"]["B"]["status"]=="NO_ONSCREEN_TITLE"
def test_trusted_is_skipped_until_weekly_recheck():
    now=datetime(2026,9,10,12,0,tzinfo=timezone.utc)
    eligible=[_row("fresh"),_row("old"),_row("new")]
    state={"channels":{"fresh":{"status":"TRUSTED","last_checked":(now-timedelta(hours=24)).isoformat()},"old":{"status":"TRUSTED","last_checked":(now-timedelta(hours=v.TRUST_RECHECK_HOURS+1)).isoformat()}}}
    names=[r["provider_name"] for r in v._select_batch(eligible,state,now)]
    assert "new" in names and "old" in names and "fresh" not in names
def test_mismatch_pending_has_highest_priority():
    now=datetime(2026,9,3,12,0,tzinfo=timezone.utc)
    chosen=v._select_batch([_row("new"),_row("bad")],{"channels":{"bad":{"status":"MISMATCH_PENDING","last_checked":now.isoformat()}}},now)
    assert chosen[0]["provider_name"]=="bad"
