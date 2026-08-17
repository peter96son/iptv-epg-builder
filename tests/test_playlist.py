from src.playlist import parse_m3u

def test_iptv_online_extgrp():
    text = """#EXTM3U
#EXTINF:0 tvg-id="Xfoo" tvg-name="Foo", Foo HD
#EXTGRP:Кино
http://example.test/foo.m3u8
"""
    items = parse_m3u(text)
    assert len(items) == 1
    assert items[0].group == "Кино"
    assert items[0].tvg_id == "Xfoo"

def test_group_title_fallback():
    text = """#EXTM3U
#EXTINF:-1 tvg-id="bar" group-title="Спорт",Bar
http://example.test/bar.m3u8
"""
    items = parse_m3u(text)
    assert items[0].group == "Спорт"

def test_extgrp_overrides_group_title():
    text = """#EXTM3U
#EXTINF:-1 tvg-id="bar" group-title="Wrong",Bar
#EXTGRP:Новости
http://example.test/bar.m3u8
"""
    items = parse_m3u(text)
    assert items[0].group == "Новости"
