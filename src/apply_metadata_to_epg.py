from __future__ import annotations

import argparse
import csv
import gzip
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .metadata_enrichment import enrich_metadata


def _load_mappings(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_epg(path: Path) -> ET.Element:
    if not path.exists():
        raise FileNotFoundError(f"Missing current EPG: {path}")
    with gzip.open(path, "rb") as f:
        return ET.parse(f).getroot()


def _write_epg_atomic(path: Path, tv: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="epg-final-", suffix=".xml.gz", dir=path.parent)
    os.close(fd)
    tmp = Path(name)
    try:
        with gzip.open(tmp, "wb", compresslevel=6) as gz:
            ET.ElementTree(tv).write(gz, encoding="utf-8", xml_declaration=True)
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = root / "output"
    epg_path = output / "epg.xml.gz"
    mappings = _load_mappings(output / "mapping.csv")
    tv = _load_epg(epg_path)

    # Final pass is local-only: backfill has already populated SQLite.
    os.environ["METADATA_MAX_TITLES"] = "0"
    os.environ["METADATA_MAX_HTTP_REQUESTS"] = "0"
    os.environ["METADATA_MULTI_FALLBACK"] = "0"

    report = enrich_metadata(tv, mappings, root, output)
    _write_epg_atomic(epg_path, tv)

    summary = report.get("summary", {})
    print(
        "[finalize-epg] "
        f"sqlite_hits={summary.get('sqlite_title_hits', 0)} "
        f"enriched={summary.get('programmes_enriched', 0)} "
        f"matches={summary.get('metadata_matches', 0)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
