from src.playlist_diff import compare_snapshots

def test_playlist_diff():
    old = [
        {"name":"A","tvg_id":"a","group":"G1","stream_url":"u1"},
        {"name":"B","tvg_id":"b","group":"G1","stream_url":"u2"},
    ]
    new = [
        {"name":"A2","tvg_id":"a","group":"G2","stream_url":"u1-new"},
        {"name":"C","tvg_id":"c","group":"G1","stream_url":"u3"},
    ]
    d = compare_snapshots(old, new)
    assert d["added_count"] == 1
    assert d["removed_count"] == 1
    assert d["renamed_count"] == 1
    assert d["stream_url_changed_count"] == 1
    assert d["group_changed_count"] == 1
