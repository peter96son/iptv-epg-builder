from pathlib import Path
from types import SimpleNamespace

from src import config
from src.matcher import Matcher

ROOT = Path(__file__).resolve().parents[1]


def test_live_verified_source_pins_are_locked():
    text = (ROOT / 'data' / 'source_pins.csv').read_text(encoding='utf-8')
    assert 'KLI СССР HD,Xkliussr,,,klimedia-dedicated,kli-sssr-hd,1' in text
    assert 'Premium HD,Xpremium-hd,,,premiere-group-dedicated,premium-hd,1' in text
    assert 'BCU СССР HD,Xbcu-sssr,,,iptvx-noarch,bcu-sssr,1' in text
    assert 'BCU СССР HD,Xbcu-sssr,,,iptvx-noarch,bcu-sssr-hdr' not in text


def test_dedicated_sources_are_eligible_for_ussr(monkeypatch):
    raw = [
        {'name':'iptv-online-primary','url':'x'},
        {'name':'iptvx-noarch','url':'x'},
        {'name':'klimedia-dedicated','url':'x','groups':['Кино']},
        {'name':'bcumedia-dedicated','url':'x','groups':['Кинозалы']},
    ]
    monkeypatch.setattr(config, 'load_json', lambda name: raw if name == 'sources.json' else {})
    sources = config.load_sources()
    by = {s['name']:s for s in sources}
    assert 'USSR' in by['klimedia-dedicated']['groups']
    assert 'USSR' in by['bcumedia-dedicated']['groups']
    names = [s['name'] for s in sources]
    assert 'premiere-group-dedicated' in names
    assert names.index('premiere-group-dedicated') < names.index('iptvx-noarch')


def test_premiere_group_spg_prefix_matches():
    aliases=[{
        'enabled':'1','playlist_name':'Premium HD','source':'premiere-group-dedicated',
        'source_id':'premium-hd','hard_pin':'1','provider_group':'','region':''
    }]
    matcher=Matcher(aliases)
    ch=SimpleNamespace(name='Premium HD',tvg_name='Premium HD',tvg_id='Xpremium-hd',group='Кинозалы')
    source=SimpleNamespace(
        name='premiere-group-dedicated',
        channels={'some-spg-id':object()},
        names={'spg premium':{'some-spg-id'}}
    )
    sid,method,confidence=matcher.match(ch,source,{'groups':['Кинозалы']},allow_family=False)
    assert sid=='some-spg-id'
    assert method=='name'
    assert confidence==90
