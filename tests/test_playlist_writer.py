from src.playlist_writer import build_uhf_playlist

def test_rewrites_header_and_known_tvg_id_only():
    original = """#EXTM3U url-tvg="https://old.example/epg.xml.gz"
#EXTINF:0 tvg-id="broken" tvg-name="Magic Horror", Magic Horror
#EXTGRP:Кинозалы
https://stream.example/magic.m3u8
#EXTINF:0 tvg-name="Unknown", Unknown
#EXTGRP:Кино
https://stream.example/unknown.m3u8
"""
    result, stats = build_uhf_playlist(
        original,
        {"Magic Horror": "Xmagic-horror"},
        "https://raw.example/epg.xml.gz",
    )
    assert 'url-tvg="https://raw.example/epg.xml.gz"' in result
    assert 'tvg-id="Xmagic-horror"' in result
    assert '#EXTGRP:Кинозалы' in result
    assert 'https://stream.example/magic.m3u8' in result
    assert 'tvg-name="Unknown"' in result
    assert stats.channels_seen == 2
    assert stats.ids_changed == 1

def test_adds_tvg_id_when_missing_and_mapping_known():
    original = """#EXTM3U
#EXTINF:0 tvg-name="Foo", Foo
#EXTGRP:Кино
https://stream.example/foo.m3u8
"""
    result, stats = build_uhf_playlist(
        original,
        {"Foo": "foo-epg"},
        "https://raw.example/epg.xml.gz",
    )
    assert 'tvg-id="foo-epg"' in result
    assert stats.ids_added == 1
