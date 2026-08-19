from __future__ import annotations

import gzip
import io
import os
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from .utils import open_xml_bytes, normalize_name, xmltv_date_is_fresh, xmltv_programme_is_usable


SPILL_THRESHOLD_BYTES = int(os.environ.get("XMLTV_SPILL_THRESHOLD_BYTES", str(4 * 1024 * 1024)))


class _OwnedGzipFile(gzip.GzipFile):
    """gzip stream that also owns/closes the underlying raw file handle."""

    def __init__(self, raw):
        self._owned_raw = raw
        super().__init__(fileobj=raw, mode="rb")

    def close(self):
        try:
            super().close()
        finally:
            raw = getattr(self, "_owned_raw", None)
            self._owned_raw = None
            if raw is not None:
                raw.close()


class XMLTVSource:
    """Indexed XMLTV source with bounded in-memory raw payload retention.

    v11.2:
    - large source payloads are spilled to a temporary file after indexing;
    - spilled sources are parsed directly from disk (not read back into one big bytes object);
    - iterparse clears the root as top-level records are consumed.
    """

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self._spill_path: Path | None = None
        self.size = len(data or b"")
        self.channels = {}
        self.names = defaultdict(set)
        self.live_ids = set()
        self.usable_ids = set()

    @property
    def data(self) -> bytes:
        """Compatibility accessor.

        Avoid this on large sources during normal operation; parsing uses _open().
        """
        if self._data is not None:
            return self._data
        if self._spill_path is not None:
            return self._spill_path.read_bytes()
        return b""

    def _spill(self) -> None:
        if self._data is None or len(self._data) < SPILL_THRESHOLD_BYTES:
            return
        try:
            fd, path = tempfile.mkstemp(prefix="epg-src-", suffix=".xmltv")
            with os.fdopen(fd, "wb") as f:
                f.write(self._data)
            self._spill_path = Path(path)
            self._data = None
        except OSError:
            self._spill_path = None

    def _open(self):
        if self._data is not None:
            return open_xml_bytes(self._data)

        if self._spill_path is None:
            return io.BytesIO(b"")

        raw = self._spill_path.open("rb")
        try:
            magic = raw.read(2)
            raw.seek(0)
            if magic == b"\x1f\x8b":
                return _OwnedGzipFile(raw)
            return raw
        except Exception:
            raw.close()
            raise

    def release(self) -> None:
        self._data = None
        if self._spill_path is not None:
            try:
                self._spill_path.unlink()
            except OSError:
                pass
            self._spill_path = None

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass

    def index(self):
        all_channels = {}
        all_names = defaultdict(set)

        f = self._open()
        try:
            context = ET.iterparse(f, events=("start", "end"))
            try:
                _, root = next(context)
            except StopIteration:
                return self

            for event, elem in context:
                if event != "end":
                    continue
                tag = elem.tag.split("}")[-1]

                if tag == "channel":
                    cid = elem.get("id", "")
                    if cid:
                        all_channels[cid] = deepcopy(elem)
                        for dn in elem.findall("display-name"):
                            if dn.text:
                                n = normalize_name(dn.text)
                                if n:
                                    all_names[n].add(cid)
                    elem.clear()
                    root.clear()

                elif tag == "programme":
                    cid = elem.get("channel", "")
                    if cid and xmltv_date_is_fresh(elem.get("start", "")):
                        self.live_ids.add(cid)
                    if cid and xmltv_programme_is_usable(
                        elem.get("start", ""), elem.get("stop", "")
                    ):
                        self.usable_ids.add(cid)
                    elem.clear()
                    root.clear()
        finally:
            f.close()

        self.channels = {
            k: v for k, v in all_channels.items()
            if k in self.usable_ids
        }
        self.names = {
            k: (v & self.usable_ids)
            for k, v in all_names.items()
            if v & self.usable_ids
        }

        self._spill()
        return self

    def fresh_programmes(self, wanted_ids: set[str], past_days=2, future_days=21):
        if not wanted_ids:
            return

        f = self._open()
        try:
            context = ET.iterparse(f, events=("start", "end"))
            try:
                _, root = next(context)
            except StopIteration:
                return

            for event, elem in context:
                if event != "end":
                    continue
                if elem.tag.split("}")[-1] == "programme":
                    cid = elem.get("channel", "")
                    if (
                        cid in wanted_ids
                        and xmltv_date_is_fresh(
                            elem.get("start", ""), past_days, future_days
                        )
                    ):
                        yield deepcopy(elem)
                    elem.clear()
                    root.clear()
        finally:
            f.close()
