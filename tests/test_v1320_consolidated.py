import csv, json
from pathlib import Path

def _pins():
    with Path("data/source_pins.csv").open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def test_fresh_family_is_fully_pinned():
    expected={f"Fresh {x}" for x in [
        "Fantastic","Vhs","Rating","Family","Premiere","Comedy","Kids","Cinema",
        "Horror","Adventure","Romantic","Russian","Thriller"
    ]}
    # Fresh VHS capitalization is special.
    expected.remove("Fresh Vhs")
    expected.add("Fresh VHS")
    rows={r["playlist_name"]:r for r in _pins()}
    assert expected <= set(rows)
    for name in expected:
        assert rows[name]["hard_pin"]=="1"
        assert rows[name]["source_id"].startswith("fresh-")

def test_magic_provider_family_is_fully_pinned():
    expected={f"Magic {x}" for x in [
        "Premiere","Adventure","Russian","Action","Comedy","Family","Galaxy",
        "Horror","Karate","Love","Thriller","VHS","Disney"
    ]}
    rows={r["playlist_name"]:r for r in _pins()}
    assert expected <= set(rows)
    for name in expected:
        assert rows[name]["source"]=="openbox-tsd"
        assert rows[name]["source_id"].startswith("magic-")
    assert "Magic TV" not in expected
    assert "jk_Magic" not in expected

def test_bcu_alias_identity_rules():
    rows={r["playlist_name"]:r for r in _pins()}
    assert rows["BCU Media OLD"]["source_id"]=="box-hybrid"
    assert rows["BCU_UTIFY_1_HDR"]["source_id"]=="bcu-comedy"
    assert rows["BCU_UTIFY_2_HD"]["source_id"]=="bcu-catastrophe"
    assert rows["BCU_UTIFY_3_HD"]["source_id"]=="bcu-history"

    rules=json.loads(Path("data/playlist_rules.json").read_text(encoding="utf-8"))
    names=rules["name_overrides"]
    assert "BCU_UTIFY_1_HDR" not in names
    assert names["BCU_UTIFY_2_HD"]=="BCU Catastrophe HD"
    assert names["BCU_UTIFY_3_HD"]=="BCU History HD"
    assert names["BCU Premiere 3 HDR"]=="BCU Fantastic HDR"
