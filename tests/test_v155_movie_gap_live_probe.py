import csv
import inspect

from src.movie_gap_live_probe import _find_exact,_load_gaps,_parse_m3u
import src.movie_gap_live_probe as m


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


def test_capture_is_single_connection_with_spaced_frames():
    source=inspect.getsource(m._capture_frames)
    assert '"-t","49"' in source
    assert '"-frames:v","3"' in source
    assert "timeout=65" in source
    assert "fps=fps=1/20:start_time=5" in source
    assert m.FRAME_SECONDS==(5,25,45)


def test_all_non_ok_movie_audit_statuses_are_monitored(tmp_path):
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
    source=inspect.getsource(m.main)
    assert 'gap.get("provider_name")' in source
    assert '_find_exact(playlist,provider_name)' in source


def test_url_metadata_is_redacted():
    assert m._redact_metadata("watch https://secret.example/a?token=x now")=="watch [URL] now"


def test_unlimited_gap_mode_is_default():
    assert m.MAX_CHANNELS==0
    assert m.MAX_WORKERS==4


def test_paddle_and_corner_ocr_are_enabled():
    assert "top_left" in m.OCR_VARIANTS
    assert "left_bottom" in m.OCR_VARIANTS
    source=inspect.getsource(m._ocr_frame)
    assert "_paddle_ocr(img)" in source
    assert "_tesseract(best,11)" in source

def test_adaptive_ocr_prefers_correct_corner():
    assert m._variant_plan("Insomnia HD")[0]=="top_left_tight"
    assert m._variant_plan("Premiere HD")[0]=="top_left_tight"
    assert m._variant_plan("DITV КОМЕДИИ СССР")[0]=="left_bottom_tight"

def test_fast_ocr_has_no_full_variant_loop():
    source=inspect.getsource(m._ocr_frame)
    assert "for variant,flt in OCR_VARIANTS.items()" not in source
