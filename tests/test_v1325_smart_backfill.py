from src.metadata_backfill_v1325 import _clean_backfill_title,_skip_row

def test_generated_rating_suffix_removed():
    assert _clean_backfill_title("Веном (2018) · IMDb 6.6","2018")==("Веном","2018")
    assert _clean_backfill_title("Хищник (1987) · IMDb 7.8","")==("Хищник","1987")

def test_generic_episode_labels_are_skipped():
    assert _skip_row("Сезон 1, Епізод 2")
    assert _skip_row("Сезон 3, Эпизод 4")
    assert _skip_row("Програма відсутня або її немає")

def test_real_russian_movies_are_not_skipped():
    assert not _skip_row("Шерлок Холмс")
    assert not _skip_row("День независимости")
