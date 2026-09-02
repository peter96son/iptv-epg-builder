import src.epg_live_audit as a

def test_premium_policy_fallback_allowed(tmp_path):
    p=tmp_path/"policy.csv"
    p.write_text("enabled,playlist_name,source,source_id\n1,Premium HD,premiere-group-dedicated,premium-hd\n1,Premium HD,gabbarit-mirror,Premium HD\n",encoding="utf-8")
    allowed=a._policy_bindings(p)
    assert ("gabbarit-mirror","Premium HD") in allowed["Premium HD"]

def test_disabled_candidate_not_allowed(tmp_path):
    p=tmp_path/"policy.csv"
    p.write_text("enabled,playlist_name,source,source_id\n1,Premium HD,premiere-group-dedicated,premium-hd\n0,Premium HD,bad,bad\n",encoding="utf-8")
    allowed=a._policy_bindings(p)
    assert ("bad","bad") not in allowed["Premium HD"]

def test_strict_verified_preserved():
    assert a.STRICT_VERIFIED["BCU СССР HD"]["source_id"]=="bcu-sssr"
    assert a.STRICT_VERIFIED["KLI СССР HD"]["source_id"]=="kli-sssr-hd"

def test_legacy_verified_export_is_preserved():
    from src.epg_live_audit import VERIFIED
    assert VERIFIED is a.STRICT_VERIFIED
    assert VERIFIED["BCU СССР HD"]["source"]=="iptvx-noarch"
