import src.movie_gap_live_probe as m

def test_frame_spacing():
    assert m.FRAME_SECONDS==(5,25,45)

def test_both_corner_families():
    assert "top_left" in m.OCR_VARIANTS
    assert "left_bottom" in m.OCR_VARIANTS

def test_exact_vhs_not_bcu():
    rows=m._parse_m3u('#EXTM3U\n#EXTINF:-1 tvg-id="Xvhshd",VHS HD\nhttp://x/v\n#EXTINF:-1 tvg-id="bcu-vhs",BCU VHS HD\nhttp://x/b\n')
    assert m._find_exact(rows,"VHS HD")["tvg_id"]=="Xvhshd"

def test_legacy_paddle_shape_parser():
    raw=[]
    m._extract_strings([[None,("ИГЛА",0.99)]],raw)
    assert raw==["ИГЛА"]

def test_v3_paddle_shape_parser():
    raw=[]
    m._extract_strings({"rec_texts":["ИГЛА","1988"]},raw)
    assert "ИГЛА" in raw


def test_v3_parser_does_not_duplicate_rec_texts():
    raw=[]
    m._extract_strings({"rec_texts":["ИГЛА"],"nested":{"rec_texts":["ДУБЛЬ"]}},raw)
    assert raw==["ИГЛА"]


def test_paddle_inference_has_lock():
    import inspect
    source=inspect.getsource(m._paddle_ocr)
    assert "_PADDLE_RUN_LOCK" in source
