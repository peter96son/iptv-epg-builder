from __future__ import annotations

import gzip
import os
from pathlib import Path

from src.xmltv import XMLTVSource


def test_spilled_gzip_close_closes_underlying_fd(monkeypatch):
    monkeypatch.setattr("src.xmltv.SPILL_THRESHOLD_BYTES", 1)
    raw = b"<tv>" + b" " * 100 + b"</tv>"
    src = XMLTVSource("gzip", gzip.compress(raw))
    src._spill()

    f = src._open()
    owned = f._owned_raw
    assert not owned.closed
    assert f.read() == raw
    f.close()
    assert owned.closed
    src.release()


def test_release_drops_small_in_memory_payload():
    src = XMLTVSource("small", b"<tv></tv>")
    assert src._data is not None
    src.release()
    assert src._data is None
    assert src._spill_path is None


def test_workflow_uses_safer_source_caps():
    workflow = Path(".github/workflows/update.yml").read_text(encoding="utf-8")
    assert 'EPG_SOURCE_TIMEOUT_CAP: "90"' in workflow
    assert 'EPG_SOURCE_DEADLINE_SECONDS: "1500"' in workflow
