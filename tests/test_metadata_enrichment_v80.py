import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import src.metadata_enrichment as m


def test_alias_file_and_variants(tmp_path):
    (tmp_path/'data').mkdir()
    (tmp_path/'data'/'metadata_aliases.json').write_text(json.dumps({
        'aliases': {'Люди в черном: Интернэшнл':['Men in Black: International']}
    }, ensure_ascii=False), encoding='utf-8')
    aliases=m._load_metadata_aliases(tmp_path)
    assert m._alias_variants('Люди в черном: Интернэшнл', aliases)==['Men in Black: International']


def test_ambiguous_single_word_threshold_is_strict():
    assert m._candidate_threshold('Хаос','') >= 0.92
    assert m._candidate_threshold('Купель дьявола','') < 0.90


def test_confidence_penalizes_cross_type():
    a=m._confidence_from_candidate(1.0,'Кремень','Кремень','','','localized+year')
    b=m._confidence_from_candidate(1.0,'Кремень','Кремень','','','cross-type+year')
    assert a > b


def test_progressive_negative_cache_backoff():
    now=datetime.now(timezone.utc)
    e={'status':'not_found','miss_count':4,'cached_at':(now-timedelta(days=10)).isoformat()}
    assert m._negative_cache_fresh(e)
    e['cached_at']=(now-timedelta(days=31)).isoformat()
    assert not m._negative_cache_fresh(e)


def test_tmdb_lookup_uses_curated_alias(monkeypatch):
    seen=[]
    def search(key,title,year,media_type,language='en-US',timeout=12):
        seen.append(title)
        if title=='Men in Black: International':
            return {'results':[{'id':1,'title':'Men in Black: International','original_title':'Men in Black: International','release_date':'2019-01-01'}]}
        return {'results':[]}
    monkeypatch.setattr(m,'_tmdb_search',search)
    monkeypatch.setattr(m,'_tmdb_external_ids',lambda *a,**k:{'imdb_id':'tt2283336'})
    aliases={m.normalize_name('Люди в черном: Интернэшнл'):['Men in Black: International']}
    r=m._tmdb_lookup_imdb('k','Люди в черном: Интернэшнл','','movie','ru-RU',budget=m._Budget(50),aliases=aliases)
    assert r['status']=='found'
    assert r['imdb_id']=='tt2283336'
    assert 'Men in Black: International' in seen
    assert r['confidence'] >= 90
