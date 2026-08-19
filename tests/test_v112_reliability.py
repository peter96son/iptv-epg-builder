
from __future__ import annotations

import gzip
from pathlib import Path

from src import metadata_quality_patch as qp
from src.xmltv import XMLTVSource


def test_trusted_legacy_identity_is_preserved_for_display_refresh():
    entry = qp._sanitize_cache_entry_v11({
        "status": "found",
        "imdb_id": "tt2283336",
        "resolver": "tmdb",
        "confidence": 98,
        "title": "Men in Black: International",
        "genre_ids": [],
        "overview": "",
    })
    assert entry["status"] == "found"
    assert entry["imdb_id"] == "tt2283336"
    assert entry["needs_display_refresh"] is True


def test_untrusted_legacy_identity_without_confidence_is_revalidated():
    entry = qp._sanitize_cache_entry_v11({
        "status": "found",
        "imdb_id": "tt1234567",
        "resolver": "tmdb",
    })
    assert entry["status"] == "legacy_unscored"
    assert entry["legacy_imdb_id"] == "tt1234567"


def test_xmltv_large_payload_spills_and_reopens_from_disk(monkeypatch):
    monkeypatch.setattr("src.xmltv.SPILL_THRESHOLD_BYTES", 64)

    raw = (
        b'<?xml version="1.0" encoding="UTF-8"?>\\n'
        b'<tv>\\n'
        b'  <channel id="c1"><display-name>Channel 1</display-name></channel>\\n'
        b'  <programme channel="c1" start="20990101000000 +0000" stop="20990101010000 +0000">\\n'
        b'    <title>Test</title>\\n'
        b'  </programme>\\n'
        b'</tv>'
    )
    src = XMLTVSource("test", raw)
    src._spill()
    assert src._data is None
    assert src._spill_path is not None
    assert src._spill_path.exists()

    f = src._open()
    try:
        assert f.read(5).startswith(b"<?xml")
    finally:
        f.close()

    path = src._spill_path
    src.release()
    assert not path.exists()


def test_xmltv_gzip_spill_is_streamed(monkeypatch):
    monkeypatch.setattr("src.xmltv.SPILL_THRESHOLD_BYTES", 16)
    raw = b"<tv>" + (b" " * 200) + b"</tv>"
    payload = gzip.compress(raw)

    src = XMLTVSource("gzip", payload)
    src._spill()
    assert src._data is None

    f = src._open()
    try:
        assert f.read() == raw
    finally:
        f.close()
    src.release()
