from src.worker_audit import audit_playlist, _fresh_url


def test_fresh_url_adds_bypass_flag():
    assert _fresh_url("https://example.com/tv") == "https://example.com/tv?fresh=1"
    assert _fresh_url("https://example.com/tv?x=1&fresh=0").endswith("x=1&fresh=1")


def test_worker_audit_detects_wrong_id_and_protected_hint():
    m3u = '''#EXTM3U\n#EXTINF:0 tvg-id="wrong",Channel A\n#EXTGRP:Россия\nhttp://a\n#EXTINF:0 tvg-id="junk" tvg-name="Junk",VeleS Test\n#EXTGRP:Кинозалы\nhttp://b\n'''
    rows, summary = audit_playlist(m3u, {"Channel A": "right"}, {"right"})
    by_name = {r["playlist_name"]: r for r in rows}
    assert by_name["Channel A"]["status"] == "wrong_tvg_id"
    assert "protected_unmatched_has_epg_hint" in by_name["VeleS Test"]["status"]
    assert summary["gap_rows"] == 2


def test_worker_audit_clean_delivery():
    m3u = '''#EXTM3U\n#EXTINF:0 tvg-id="right",Channel A\n#EXTGRP:Россия\nhttp://a\n#EXTINF:0,VeleS Test\n#EXTGRP:Кинозалы\nhttp://b\n'''
    rows, summary = audit_playlist(m3u, {"Channel A": "right"}, {"right"})
    assert all(r["status"] == "ok" for r in rows)
    assert summary["gap_rows"] == 0
