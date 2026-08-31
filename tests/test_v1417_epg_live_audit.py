from src.epg_live_audit import VERIFIED
def test_bcu_exact_binding_and_hdr_forbidden():
 v=VERIFIED["BCU СССР HD"]; assert v["source"]=="iptvx-noarch"; assert v["source_id"]=="bcu-sssr"; assert "bcu-sssr-hdr" in v["forbidden"]
