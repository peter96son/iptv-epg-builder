from pathlib import Path

from src.config import load_aliases, load_sources


def test_kli_pin_with_note_is_not_dropped():
    rows = [r for r in load_aliases() if r.get("playlist_name") == "KLI СССР HD"]
    assert rows
    assert any(r.get("source") == "klimedia-dedicated" and r.get("hard_pin") == "1" for r in rows)


def test_dead_v1415_rescues_removed_and_m3uedit_added():
    sources = {s["name"]: s for s in load_sources()}
    for dead in ("ottepg-rescue", "kineskop-rescue", "shara-tv-rescue"):
        assert dead not in sources
    m = sources["m3u-edit-all-rescue"]
    assert m["rescue_source"] is True
    assert m["groups"] == ["Кино", "USSR", "Кинозалы", "Кино 4K"]
    assert "ALL_SOURCES1.xml.gz" in m["url"]


def test_source_pins_csv_has_no_unquoted_extra_column_on_kli_row():
    line = (Path(__file__).resolve().parents[1] / "data" / "source_pins.csv").read_text(encoding="utf-8").splitlines()[1]
    assert line.count(",") == 8
