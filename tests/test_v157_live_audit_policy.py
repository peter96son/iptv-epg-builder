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
    assert a.STRICT_VERIFIED["KLI СССР HD"]=={"source":"tvteam","source_id":"ch4083","forbidden":set()}
    assert a.STRICT_VERIFIED["KBC-Страна СССР"]=={"source":"gabbarit-current","source_id":"KBC-Страна СССР","forbidden":set()}

def test_legacy_verified_export_is_preserved():
    from src.epg_live_audit import VERIFIED
    assert VERIFIED is a.STRICT_VERIFIED
    assert VERIFIED["BCU СССР HD"]["source"]=="iptvx-noarch"

def test_strict_targets_missing_from_mapping_are_reported(tmp_path, monkeypatch):
    import gzip
    monkeypatch.setattr(a, "OUT", tmp_path)
    (tmp_path / "mapping.csv").write_text(
        "playlist_name,group,source,source_id,output_tvg_id\nOther,Кино,x,y,other\n",
        encoding="utf-8",
    )
    with gzip.open(tmp_path / "epg.xml.gz", "wb") as f:
        f.write(b"<tv></tv>")

    result = a.build(now=__import__("datetime").datetime(2026, 11, 25, 23, 0, tzinfo=__import__("datetime").timezone.utc), strict=False)

    assert any("KBC-Страна СССР: missing from mapping.csv" in e for e in result["verified_errors"])
    assert any("KLI СССР HD: missing from mapping.csv" in e for e in result["verified_errors"])
