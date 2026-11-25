from pathlib import Path
from src.movie_epg_audit import _provider_catchup_info
from src.playlist import parse_m3u

def test_live_ocr_current_does_not_require_fake_next():
    x=(Path(__file__).resolve().parents[1]/"src"/"movie_epg_audit.py").read_text(encoding="utf-8")
    assert "live_ocr_current=any(" in x
    assert "if cid and arr and not future and not live_ocr_current:" in x


def test_provider_archive_settings_can_be_read_from_global_or_channel_tags():
    playlist = '''#EXTM3U catchup="append" catchup-days="7"
#EXTINF:-1 tvg-id="one" group-title="Кино",Cinema One
https://example.invalid/live
#EXTINF:-1 tvg-id="two" catchup="default" catchup-days="3" group-title="USSR",Cinema Two
https://example.invalid/live2
'''
    one, two = parse_m3u(playlist)

    assert _provider_catchup_info(playlist, one) == ("append", "7")
    assert _provider_catchup_info(playlist, two) == ("default", "3")
