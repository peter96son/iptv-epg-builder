import json
from src.epg_horizon_audit import _prune_fatal_mappings

def test_prune_fatal_only(tmp_path):
    p=tmp_path/"map.json"
    p.write_text(json.dumps({"epg_url":"x","channels":{"Good":"g","Short":"s","Stale":"t","Empty":"e"}}),encoding="utf-8")
    rows=[{"playlist_name":"Good","status":"OK"},{"playlist_name":"Short","status":"EXPIRING_SOON"},{"playlist_name":"Stale","status":"STALE"},{"playlist_name":"Empty","status":"NO_PROGRAMMES"}]
    removed=_prune_fatal_mappings(p,rows)
    data=json.loads(p.read_text(encoding="utf-8"))
    assert set(removed)=={"Stale","Empty"}
    assert data["channels"]=={"Good":"g","Short":"s"}
    assert data["epg_url"]=="x"
