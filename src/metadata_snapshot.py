from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .metadata_db import DEFAULT_DB_NAME


SNAPSHOT_PATH = Path("data") / f"{DEFAULT_DB_NAME}.gz"


def db_path(root: Path) -> Path:
    return root / ".cache" / "metadata" / DEFAULT_DB_NAME


def snapshot_path(root: Path) -> Path:
    return root / SNAPSHOT_PATH


def restore_snapshot(root: Path, *, force: bool = True) -> bool:
    """Restore the git snapshot into the working cache.

    Git is the durable source of truth. Cache remains an acceleration layer for
    XMLTV/IMDb artifacts, but metadata.sqlite3 starts from the checked-in snapshot.
    """
    src = snapshot_path(root)
    dst = db_path(root)
    if not src.exists():
        return False
    if dst.exists() and not force:
        return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".restore")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass

    with gzip.open(src, "rb") as inp, tmp.open("wb") as out:
        shutil.copyfileobj(inp, out)
    tmp.replace(dst)
    return True


def save_snapshot(root: Path) -> bool:
    """Create a deterministic gzip snapshot from a consistent SQLite backup."""
    src = db_path(root)
    if not src.exists():
        return False

    dst = snapshot_path(root)
    dst.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="metadata-snapshot-") as td:
        backup = Path(td) / DEFAULT_DB_NAME

        source = sqlite3.connect(src)
        try:
            source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target = sqlite3.connect(backup)
            try:
                source.backup(target)
                target.commit()
            finally:
                target.close()
        finally:
            source.close()

        tmp = dst.with_suffix(dst.suffix + ".tmp")
        with backup.open("rb") as inp, tmp.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
                shutil.copyfileobj(inp, gz)
        tmp.replace(dst)

    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("restore", "save"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--if-missing", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.action == "restore":
        changed = restore_snapshot(root, force=not args.if_missing)
    else:
        changed = save_snapshot(root)

    print(f"[metadata-snapshot] {args.action}: {'ok' if changed else 'nothing-to-do'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
