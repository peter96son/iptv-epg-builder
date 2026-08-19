from __future__ import annotations

import gzip
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from src.metadata_backfill import build_queue
from src.metadata_db import open_metadata_db
from src.metadata_snapshot import restore_snapshot, save_snapshot


def test_snapshot_roundtrip(tmp_path: Path):
    with open_metadata_db(tmp_path) as db:
        db.put_title("Film", "2020", "movie", "en-US", {
            "status": "found",
            "imdb_id": "tt1234567",
            "confidence": 99,
        })

    assert save_snapshot(tmp_path)
    dbfile = tmp_path / ".cache" / "metadata" / "metadata.sqlite3"
    dbfile.unlink()

    assert restore_snapshot(tmp_path)
    with open_metadata_db(tmp_path) as db:
        row = db.get_title("Film", "2020", "movie", "en-US")
        assert row["imdb_id"] == "tt1234567"


def test_backfill_queue_deduplicates_series_episodes():
    tv = ET.Element("tv")
    for title in ("т/с След (Нарциссы)", "т/с След (Очередь)", "т/с След (Год спустя)"):
        p = ET.SubElement(tv, "programme", {"channel": "c1"})
        ET.SubElement(p, "title", {"lang": "ru"}).text = title

    queue = build_queue(tv, [{"output_tvg_id": "c1", "group": "Сериалы"}])
    assert len(queue) == 1
    assert queue[0]["title"] == "След"


def test_movie_group_has_priority_zero():
    tv = ET.Element("tv")
    p = ET.SubElement(tv, "programme", {"channel": "c1"})
    ET.SubElement(p, "title", {"lang": "ru"}).text = "Матрица"

    queue = build_queue(tv, [{"output_tvg_id": "c1", "group": "Кино"}])
    assert len(queue) == 1
    assert queue[0]["priority"] == 0


def test_workflows_share_concurrency_group():
    update = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    backfill = Path(".github/workflows/backfill-metadata.yml").read_text(encoding="utf-8")
    assert "group: epg-metadata" in update
    assert "group: epg-metadata" in backfill
    assert "python -m src.metadata_backfill" in backfill
    assert "PLAYLIST_URL" not in backfill
