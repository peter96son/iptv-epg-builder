from src.title_normalization_patch import (
    compact_uhf_title,
    normalize_existing_compact_title,
)


def test_duplicate_parenthesized_year_collapses():
    assert normalize_existing_compact_title(
        "Вечера на хуторе близ Диканьки (1961) (1961) · IMDb 7.4"
    ) == "Вечера на хуторе близ Диканьки (1961) · IMDb 7.4"


def test_bare_provider_year_collapses():
    assert normalize_existing_compact_title(
        "Морозко 1965 (1965) · IMDb 6.4"
    ) == "Морозко (1965) · IMDb 6.4"


def test_numeric_title_is_preserved():
    assert compact_uhf_title("1984 (1984) · IMDb 7.1", "1984", "7.1") == (
        "1984 (1984) · IMDb 7.1"
    )


def test_formatter_is_idempotent():
    once = compact_uhf_title("Старший сын 1975", "1975", "7.9")
    twice = compact_uhf_title(once, "1975", "7.9")
    assert once == twice == "Старший сын (1975) · IMDb 7.9"
