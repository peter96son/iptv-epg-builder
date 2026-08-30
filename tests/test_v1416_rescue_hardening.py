from pathlib import Path

from src.config import load_aliases, load_sources


def test_kli_pin_with_note_is_not_dropped():
    rows = [r for r in load_aliases() if r.get("playlist_name") == "KLI СССР HD"]
    assert rows
    row = next(r for r in rows if r.get("source") == "klimedia-dedicated")
    assert row.get("hard_pin") == "1"
    assert "not Runigma" in row.get("notes", "")


def test_dead_v1415_rescues_removed_and_m3uedit_added():
    sources = {s["name"]: s for s in load_sources()}
    for dead in ("ottepg-rescue", "kineskop-rescue", "shara-tv-rescue"):
        assert dead not in sources
    m = sources["m3u-edit-all-rescue"]
    assert m["rescue_source"] is True
    assert m["groups"] == ["Кино", "USSR", "Кинозалы", "Кино 4K"]
    assert "ALL_SOURCES1.xml.gz" in m["url"]


def test_source_pin_parser_merges_unquoted_note_tail(tmp_path):
    p = tmp_path / "pins.csv"
    p.write_text(
        "enabled,playlist_name,playlist_tvg_id,provider_group,region,source,source_id,hard_pin,notes\n"
        "1,KLI СССР HD,Xkliussr,,,klimedia-dedicated,kli-sssr-hd,1,live verified, not Runigma\n",
        encoding="utf-8",
    )
    from src.config import _read_alias_csv
    rows = _read_alias_csv(p)
    assert len(rows) == 1
    assert rows[0]["playlist_name"] == "KLI СССР HD"
    assert rows[0]["source"] == "klimedia-dedicated"
    assert rows[0]["hard_pin"] == "1"
    assert rows[0]["notes"] == "live verified, not Runigma"
