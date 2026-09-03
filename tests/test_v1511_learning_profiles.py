import src.movie_gap_live_probe as m

def test_channel_identity_filter():
    assert m._is_channel_identity("INSOMNIA HD","Insomnia HD")
    assert not m._is_channel_identity("ПЕРВАЯ ВЕДЬМА","Insomnia HD")


def test_pick_title_ignores_channel_name():
    profile={}
    candidates=[
        {"engine":"tesseract","variant":"top_left_tight","lines":["INSOMNIA HD","ПЕРВАЯ ВЕДЬМА"]}
    ]
    chosen=m._pick_title(candidates,"Insomnia HD","Insomnia HD",profile)
    assert chosen["title"]=="ПЕРВАЯ ВЕДЬМА"


def test_profile_learns_zone_and_engine():
    profile={}
    chosen={"title":"ИГРА","engine":"tesseract","zone":"top_left_tight","score":10}
    m._update_profile(profile,chosen,[],"Thriller HD","Thriller HD")
    assert profile["preferred_zone"]=="top_left_tight"
    assert profile["preferred_engine"]=="tesseract"
    assert profile["last_title"]=="ИГРА"


def test_static_text_requires_multiple_distinct_titles():
    profile={}
    logo=[{"engine":"tesseract","variant":"top_left","lines":["CHANNEL BUG"]}]
    for title in ("ИГРА","ОГОНЬ","ПЕРВАЯ ВЕДЬМА"):
        chosen={"title":title,"engine":"tesseract","zone":"top_left_tight","score":10}
        m._update_profile(profile,chosen,logo,"Some HD","Some HD")
    assert "CHANNEL BUG" in profile["static_text"]
