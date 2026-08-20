from pathlib import Path
import csv

def test_verified_schedule_fixes_are_present():
    path = Path("data/tvg_id_fixes.csv")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    fixes = {(r["playlist_name"], r["new_tvg_id"]) for r in rows if r["enabled"] == "1"}

    expected = {
        ("KLI СССР HD", "kli-sssr-hd"),
        ("Premium HD", "premium-hd"),
        ("VHS HD", "vhs-hd"),
        ("Thriller HD", "thriller-hd"),
        ("РуКино HD", "rukino-hd"),
        ("Insomnia HD", "insomnia-hd"),
        ("Hollywood HD", "hollywood-hd"),
        ("Наше любимое кино", "Xnashe-lubimoe"),
    }
    assert expected <= fixes
