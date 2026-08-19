from __future__ import annotations

import argparse
import json
from pathlib import Path

from .metadata_db import open_metadata_db


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect v13 normalized metadata knowledge layer.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--title-id", type=int)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    with open_metadata_db(root) as db:
        payload = {
            "schema_version": db.get_stat("knowledge_schema_version", ""),
            "counts": db.counts(),
            "last_migration_at": db.get_stat("knowledge_last_migration_at", ""),
            "resolution_mode": db.get_stat("knowledge_resolution_mode", ""),
            "alias_learning_version": db.get_stat("alias_learning_version", ""),
            "imdb_local_layer": db.get_stat("imdb_local_layer", ""),
        }
        if args.title_id:
            payload["title"] = db.get_knowledge_title(args.title_id)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
