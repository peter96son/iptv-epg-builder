import gzip
import json
from datetime import datetime, timezone
import src.metadata_enrichment as m


def _sample_gz(path):
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        f.write('tconst\taverageRating\tnumVotes\n')
        f.write('tt10990862\t5.7\t1234\n')
        f.write('tt0119116\t7.6\t410000\n')


def test_build_and_lookup_official_ratings_dataset(tmp_path):
    gz = tmp_path / 'ratings.tsv.gz'
    db = tmp_path / 'ratings.sqlite3'
    _sample_gz(gz)
    m._build_imdb_ratings_db(gz, db)
    conn = m._open_imdb_ratings_db(db)
    try:
        assert m._lookup_imdb_dataset(conn, 'tt10990862') == {'rating': '5.7', 'votes': '1234'}
        assert m._lookup_imdb_dataset(conn, 'tt0000000') == {'rating': '', 'votes': ''}
    finally:
        conn.close()


def test_entity_cache_avoids_repeat_dataset_lookup(monkeypatch):
    calls = {'n': 0}
    def fake(conn, iid):
        calls['n'] += 1
        return {'rating': '7.6', 'votes': '410000'}
    monkeypatch.setattr(m, '_lookup_imdb_dataset', fake)
    stats = m.Counter()
    cache = {}
    a = m._resolve_imdb_entity('tt0119116', cache, stats, object())
    b = m._resolve_imdb_entity('tt0119116', cache, stats, object())
    assert a['source'] == 'imdb-dataset'
    assert a['rating'] == '7.6' and a['votes'] == '410000'
    assert b == a and calls['n'] == 1


def test_v8_cache_migration_removes_legacy_omdb_labels(tmp_path):
    path = tmp_path / 'metadata-v80.json'
    path.write_text(json.dumps({'schema': 8, 'entries': {
        'good': {'status': 'found', 'imdb_id': 'tt10990862', 'resolver': 'tmdb+omdb', 'imdb_rating': '5.7'},
        'miss': {'status': 'not_found', 'miss_count': 2, 'cached_at': datetime.now(timezone.utc).isoformat()}
    }}), encoding='utf-8')
    got = m._load_cache(path)
    assert got['good']['resolver'] == 'tmdb'
    assert 'imdb_rating' not in got['good']
    assert got['miss']['status'] == 'not_found'


def test_stable_v9_cache_filename():
    assert m.CACHE_FILE == 'metadata-cache.json'
    assert m.IMDB_ENTITY_CACHE_FILE == 'imdb-cache.json'
