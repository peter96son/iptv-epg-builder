import json
import src.movie_gap_live_probe as m

def test_good_short_titles_pass():
    for title in ["ИГРА","Горько","ОГОНЬ","Доктор Глас","ПЕРВАЯ ВЕДЬМА","Бесславные ублюдки (2009)"]:
        assert m._looks_like_title(title), title

def test_known_garbage_is_rejected():
    for title in ['sie','ee г','TRS в','4 _f4 od . =. "ae','т a: СЗЫЫ','= ый » So .','Bint!']:
        assert not m._looks_like_title(title), title

def test_pick_title_prefers_real_title_over_noise():
    candidates=[{"engine":"tesseract","variant":"top_left_tight","lines":["ee г","ПЕРВАЯ ВЕДЬМА","INSOMNIA HD"]}]
    chosen=m._pick_title(candidates,"Insomnia HD","Insomnia HD",{})
    assert chosen["title"]=="ПЕРВАЯ ВЕДЬМА"
    assert chosen["confidence"] in {"high","medium"}

def test_profile_does_not_learn_low_confidence():
    profile={}
    chosen={"title":"сомнительно","engine":"tesseract","zone":"top_left_tight","score":8,"confidence":"low"}
    m._update_profile(profile,chosen,[],"X","X")
    assert not profile.get("last_title")

def test_load_profiles_cleans_old_garbage(tmp_path):
    p=tmp_path/"profiles.json"
    p.write_text(json.dumps({
        "A":{"last_title":"sie","title_history":["sie"],"preferred_zone":"top_left_tight","preferred_engine":"tesseract"},
        "B":{"last_title":"ИГРА","title_history":["ИГРА"],"preferred_zone":"top_left_tight","preferred_engine":"tesseract"},
    },ensure_ascii=False),encoding="utf-8")
    got=m._load_profiles(p)
    assert got["A"]["last_title"]==""
    assert got["A"]["preferred_zone"]==""
    assert got["B"]["last_title"]=="ИГРА"
