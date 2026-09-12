from pathlib import Path

def test_live_ocr_current_does_not_require_fake_next():
    x=(Path(__file__).resolve().parents[1]/"src"/"movie_epg_audit.py").read_text(encoding="utf-8")
    assert "live_ocr_current=any(" in x
    assert "if cid and arr and not future and not live_ocr_current:" in x
