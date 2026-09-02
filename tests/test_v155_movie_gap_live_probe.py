import csv
from pathlib import Path

from src.movie_gap_live_probe import _find_exact,_load_gaps,_parse_m3u


def test_only_requested_movie_groups_are_monitored(tmp_path):
    p=tmp_path/"gaps.csv"
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["group","playlist_name","status"])
        w.writeheader()
        w.writerows([
            {"group":"Кино","playlist_name":"A","status":"NO_MAPPING"},
            {"group":"USSR","playlist_name":"B","status":"NO_MAPPING"},
            {"group":"Кинозалы","playlist_name":"C","status":"NO_CURRENT_PROGRAMME"},
            {"group":"Кино 4K","playlist_name":"D","status":"NO_NEXT_PROGRAMME"},
            {"group":"Спорт","playlist_name":"E","status":"NO_MAPPING"},
            {"group":"Кино","playlist_name":"F","status":"OK"},
        ])
    assert {r["playlist_name"] for r in _load_gaps(p)}=={"A","B","C","D"}


def test_exact_vhs_never_becomes_bcu_vhs():
    rows=_parse_m3u("""#EXTM3U
#EXTINF:-1 tvg-id="Xvhshd",VHS HD
http://secret/vhs
#EXTINF:-1 tvg-id="bcu-vhs",BCU VHS HD
http://secret/bcu
""")
    assert _find_exact(rows,"VHS HD")["tvg_id"]=="Xvhshd"


def test_capture_is_single_connection_design():
    import inspect
    import src.movie_gap_live_probe as m
    source=inspect.getsource(m._capture_frames)
    assert '"-t","20"' in source
    assert '"-frames:v","3"' in source
    assert "timeout=34" in source


def test_all_non_ok_movie_audit_statuses_are_monitored(tmp_path):
    import csv
    from src.movie_gap_live_probe import _load_gaps
    p=tmp_path/"gaps.csv"
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["group","playlist_name","provider_name","status"])
        w.writeheader()
        w.writerows([
            {"group":"Кино","playlist_name":"A","provider_name":"A","status":"ID_NOT_IN_EPG"},
            {"group":"Кино","playlist_name":"B","provider_name":"B","status":"NO_PROGRAMMES"},
            {"group":"Кино","playlist_name":"C","provider_name":"C","status":"NO_CURRENT_PROGRAMME;NO_NEXT_PROGRAMME"},
            {"group":"Кино","playlist_name":"D","provider_name":"D","status":"OK"},
        ])
    assert {r["playlist_name"] for r in _load_gaps(p)}=={"A","B","C"}


def test_provider_name_is_preserved_for_name_override_rows():
    # movie_epg_audit may write playlist_name after name_overrides while
    # provider_name remains the actual M3U channel name. The verifier must have
    # both fields available and locate streams by provider_name.
    import inspect
    import src.movie_gap_live_probe as m
    source=inspect.getsource(m.main)
    assert 'gap.get("provider_name")' in source
    assert '_find_exact(playlist,provider_name)' in source


def test_url_metadata_is_redacted():
    from src.movie_gap_live_probe import _redact_metadata
    assert _redact_metadata("watch https://secret.example/a?token=x now") == "watch [URL] now"


def test_unlimited_gap_mode_is_default():
    import src.movie_gap_live_probe as m
    assert m.MAX_CHANNELS == 0
    assert m.MAX_WORKERS == 4
