from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from .utils import normalize_name

SCHEMA_VERSION = 1
DEFAULT_DB_NAME = "metadata.sqlite3"
IMDB_ID_RE = re.compile(r"(?i)^tt\d{5,12}$")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_imdb_id(value: str | None) -> str:
    value = (value or "").strip().lower()
    return value if IMDB_ID_RE.fullmatch(value) else ""


def normalize_year(value: str | int | None) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"(?:19|20)\d{2}", text) else ""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


@dataclass(frozen=True)
class TitleKey:
    title: str
    year: str
    media_type: str
    language: str

    @property
    def normalized_title(self) -> str:
        return normalize_name(self.title)


class MetadataDB:
    """Persistent SQLite cache for EPG title identity and metadata.

    The DB replaces the large JSON metadata caches while preserving the same
    conceptual split used by v10:

    * title_cache: schedule title/year/type/lang -> resolved TMDb/IMDb identity
    * imdb_entities: IMDb ID -> rating/votes and entity-level metadata
    * aliases: additional normalized titles -> a resolved IMDb identity

    All writes are UPSERTs and therefore idempotent. WAL is enabled so reads
    remain cheap while a build updates the cache.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MetadataDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.conn.execute("BEGIN")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS title_cache (
                normalized_title TEXT NOT NULL,
                display_title TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                media_type TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                imdb_id TEXT NOT NULL DEFAULT '',
                tmdb_id INTEGER,
                tmdb_title TEXT NOT NULL DEFAULT '',
                original_title TEXT NOT NULL DEFAULT '',
                overview TEXT NOT NULL DEFAULT '',
                genre_ids_json TEXT NOT NULL DEFAULT '[]',
                resolved_media_type TEXT NOT NULL DEFAULT '',
                query_title TEXT NOT NULL DEFAULT '',
                attempt TEXT NOT NULL DEFAULT '',
                resolver TEXT NOT NULL DEFAULT '',
                confidence INTEGER,
                similarity REAL,
                attempts INTEGER NOT NULL DEFAULT 0,
                miss_count INTEGER NOT NULL DEFAULT 0,
                cached_at TEXT NOT NULL DEFAULT '',
                rating_checked_at TEXT NOT NULL DEFAULT '',
                extra_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (normalized_title, year, media_type, language)
            );

            CREATE INDEX IF NOT EXISTS idx_title_cache_imdb
                ON title_cache(imdb_id);
            CREATE INDEX IF NOT EXISTS idx_title_cache_status
                ON title_cache(status);
            CREATE INDEX IF NOT EXISTS idx_title_cache_tmdb
                ON title_cache(tmdb_id);

            CREATE TABLE IF NOT EXISTS imdb_entities (
                imdb_id TEXT PRIMARY KEY,
                rating TEXT NOT NULL DEFAULT '',
                votes INTEGER,
                source TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                original_title TEXT NOT NULL DEFAULT '',
                overview TEXT NOT NULL DEFAULT '',
                genres_json TEXT NOT NULL DEFAULT '[]',
                year TEXT NOT NULL DEFAULT '',
                runtime_minutes INTEGER,
                countries_json TEXT NOT NULL DEFAULT '[]',
                poster_url TEXT NOT NULL DEFAULT '',
                kp_rating TEXT NOT NULL DEFAULT '',
                kp_votes INTEGER,
                extra_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS aliases (
                normalized_alias TEXT NOT NULL,
                alias TEXT NOT NULL DEFAULT '',
                imdb_id TEXT NOT NULL,
                year TEXT NOT NULL DEFAULT '',
                media_type TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                confidence INTEGER,
                created_at TEXT NOT NULL DEFAULT '',
                last_seen_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (normalized_alias, year, media_type),
                FOREIGN KEY (imdb_id) REFERENCES imdb_entities(imdb_id)
                    ON UPDATE CASCADE ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_alias_imdb
                ON aliases(imdb_id);
            """
        )
        self.conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Title-resolution cache
    # ------------------------------------------------------------------
    def get_title(self, title: str, year: str = "", media_type: str = "", language: str = "") -> dict | None:
        normalized = normalize_name(title)
        if not normalized:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM title_cache
            WHERE normalized_title=? AND year=? AND media_type=? AND language=?
            """,
            (normalized, normalize_year(year), media_type or "", language or ""),
        ).fetchone()
        return self._title_row_to_dict(row) if row else None

    def put_title(
        self,
        title: str,
        year: str = "",
        media_type: str = "",
        language: str = "",
        entry: dict | None = None,
    ) -> None:
        entry = dict(entry or {})
        normalized = normalize_name(title)
        if not normalized:
            return

        known = {
            "status", "imdb_id", "tmdb_id", "title", "original_title", "overview",
            "genre_ids", "resolved_media_type", "query_title", "attempt", "resolver",
            "confidence", "similarity", "attempts", "miss_count", "cached_at",
            "rating_checked_at", "imdb_rating", "imdb_votes", "rating_source",
        }
        extra = {k: v for k, v in entry.items() if k not in known}
        imdb_id = normalize_imdb_id(entry.get("imdb_id"))
        cached_at = str(entry.get("cached_at") or utcnow_iso())

        self.conn.execute(
            """
            INSERT INTO title_cache (
                normalized_title, display_title, year, media_type, language,
                status, imdb_id, tmdb_id, tmdb_title, original_title, overview,
                genre_ids_json, resolved_media_type, query_title, attempt, resolver,
                confidence, similarity, attempts, miss_count, cached_at,
                rating_checked_at, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(normalized_title, year, media_type, language) DO UPDATE SET
                display_title=excluded.display_title,
                status=excluded.status,
                imdb_id=excluded.imdb_id,
                tmdb_id=excluded.tmdb_id,
                tmdb_title=excluded.tmdb_title,
                original_title=excluded.original_title,
                overview=excluded.overview,
                genre_ids_json=excluded.genre_ids_json,
                resolved_media_type=excluded.resolved_media_type,
                query_title=excluded.query_title,
                attempt=excluded.attempt,
                resolver=excluded.resolver,
                confidence=excluded.confidence,
                similarity=excluded.similarity,
                attempts=excluded.attempts,
                miss_count=excluded.miss_count,
                cached_at=excluded.cached_at,
                rating_checked_at=excluded.rating_checked_at,
                extra_json=excluded.extra_json
            """,
            (
                normalized, title, normalize_year(year), media_type or "", language or "",
                str(entry.get("status") or ""), imdb_id,
                int(entry["tmdb_id"]) if str(entry.get("tmdb_id") or "").isdigit() else None,
                str(entry.get("title") or ""), str(entry.get("original_title") or ""),
                str(entry.get("overview") or ""), _json_dumps(entry.get("genre_ids") or []),
                str(entry.get("resolved_media_type") or ""), str(entry.get("query_title") or ""),
                str(entry.get("attempt") or ""), str(entry.get("resolver") or ""),
                int(entry["confidence"]) if str(entry.get("confidence") or "").lstrip("-").isdigit() else None,
                float(entry["similarity"]) if entry.get("similarity") not in (None, "") else None,
                int(entry.get("attempts") or 0), int(entry.get("miss_count") or 0), cached_at,
                str(entry.get("rating_checked_at") or ""), _json_dumps(extra),
            ),
        )

        # Preserve v10 entity fields when migrating/feeding old cache entries.
        if imdb_id and any(entry.get(k) not in (None, "") for k in ("imdb_rating", "imdb_votes", "rating_source")):
            self.put_imdb_entity(
                imdb_id,
                {
                    "rating": str(entry.get("imdb_rating") or ""),
                    "votes": entry.get("imdb_votes"),
                    "source": str(entry.get("rating_source") or ""),
                    "checked_at": str(entry.get("rating_checked_at") or cached_at),
                    "title": str(entry.get("title") or ""),
                    "original_title": str(entry.get("original_title") or ""),
                    "overview": str(entry.get("overview") or ""),
                    "year": str(entry.get("year") or year or ""),
                },
            )

    def delete_title(self, title: str, year: str = "", media_type: str = "", language: str = "") -> None:
        self.conn.execute(
            "DELETE FROM title_cache WHERE normalized_title=? AND year=? AND media_type=? AND language=?",
            (normalize_name(title), normalize_year(year), media_type or "", language or ""),
        )

    def _title_row_to_dict(self, row: sqlite3.Row) -> dict:
        out = {
            "status": row["status"],
            "imdb_id": row["imdb_id"],
            "tmdb_id": row["tmdb_id"],
            "title": row["tmdb_title"],
            "original_title": row["original_title"],
            "overview": row["overview"],
            "genre_ids": _json_loads(row["genre_ids_json"], []),
            "resolved_media_type": row["resolved_media_type"],
            "query_title": row["query_title"],
            "attempt": row["attempt"],
            "resolver": row["resolver"],
            "confidence": row["confidence"],
            "similarity": row["similarity"],
            "attempts": row["attempts"],
            "miss_count": row["miss_count"],
            "cached_at": row["cached_at"],
            "rating_checked_at": row["rating_checked_at"],
        }
        out.update(_json_loads(row["extra_json"], {}))
        return out

    # ------------------------------------------------------------------
    # IMDb entity cache
    # ------------------------------------------------------------------
    def get_imdb_entity(self, imdb_id: str) -> dict | None:
        iid = normalize_imdb_id(imdb_id)
        if not iid:
            return None
        row = self.conn.execute("SELECT * FROM imdb_entities WHERE imdb_id=?", (iid,)).fetchone()
        if not row:
            return None
        out = {
            "rating": row["rating"],
            "votes": "" if row["votes"] is None else str(row["votes"]),
            "source": row["source"],
            "checked_at": row["checked_at"],
            "title": row["title"],
            "original_title": row["original_title"],
            "overview": row["overview"],
            "genres": _json_loads(row["genres_json"], []),
            "year": row["year"],
            "runtime_minutes": row["runtime_minutes"],
            "countries": _json_loads(row["countries_json"], []),
            "poster_url": row["poster_url"],
            "kp_rating": row["kp_rating"],
            "kp_votes": "" if row["kp_votes"] is None else str(row["kp_votes"]),
        }
        out.update(_json_loads(row["extra_json"], {}))
        return out

    def put_imdb_entity(self, imdb_id: str, entity: dict | None = None) -> None:
        entity = dict(entity or {})
        iid = normalize_imdb_id(imdb_id)
        if not iid:
            return

        known = {
            "rating", "votes", "source", "checked_at", "title", "original_title",
            "overview", "genres", "year", "runtime_minutes", "countries", "poster_url",
            "kp_rating", "kp_votes",
        }
        extra = {k: v for k, v in entity.items() if k not in known}

        def to_int(value: Any) -> int | None:
            text = str(value or "").replace(",", "").replace(" ", "").strip()
            return int(text) if text.isdigit() else None

        self.conn.execute(
            """
            INSERT INTO imdb_entities (
                imdb_id, rating, votes, source, checked_at, title, original_title,
                overview, genres_json, year, runtime_minutes, countries_json,
                poster_url, kp_rating, kp_votes, extra_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(imdb_id) DO UPDATE SET
                rating=excluded.rating,
                votes=excluded.votes,
                source=excluded.source,
                checked_at=excluded.checked_at,
                title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE imdb_entities.title END,
                original_title=CASE WHEN excluded.original_title<>'' THEN excluded.original_title ELSE imdb_entities.original_title END,
                overview=CASE WHEN excluded.overview<>'' THEN excluded.overview ELSE imdb_entities.overview END,
                genres_json=CASE WHEN excluded.genres_json<>'[]' THEN excluded.genres_json ELSE imdb_entities.genres_json END,
                year=CASE WHEN excluded.year<>'' THEN excluded.year ELSE imdb_entities.year END,
                runtime_minutes=COALESCE(excluded.runtime_minutes, imdb_entities.runtime_minutes),
                countries_json=CASE WHEN excluded.countries_json<>'[]' THEN excluded.countries_json ELSE imdb_entities.countries_json END,
                poster_url=CASE WHEN excluded.poster_url<>'' THEN excluded.poster_url ELSE imdb_entities.poster_url END,
                kp_rating=CASE WHEN excluded.kp_rating<>'' THEN excluded.kp_rating ELSE imdb_entities.kp_rating END,
                kp_votes=COALESCE(excluded.kp_votes, imdb_entities.kp_votes),
                extra_json=excluded.extra_json
            """,
            (
                iid, str(entity.get("rating") or ""), to_int(entity.get("votes")),
                str(entity.get("source") or ""), str(entity.get("checked_at") or utcnow_iso()),
                str(entity.get("title") or ""), str(entity.get("original_title") or ""),
                str(entity.get("overview") or ""), _json_dumps(entity.get("genres") or []),
                normalize_year(entity.get("year")), to_int(entity.get("runtime_minutes")),
                _json_dumps(entity.get("countries") or []), str(entity.get("poster_url") or ""),
                str(entity.get("kp_rating") or ""), to_int(entity.get("kp_votes")), _json_dumps(extra),
            ),
        )

    # ------------------------------------------------------------------
    # Aliases / learning
    # ------------------------------------------------------------------
    def get_alias(self, alias: str, year: str = "", media_type: str = "") -> dict | None:
        normalized = normalize_name(alias)
        if not normalized:
            return None
        row = self.conn.execute(
            """
            SELECT * FROM aliases
            WHERE normalized_alias=? AND year=? AND media_type=?
            """,
            (normalized, normalize_year(year), media_type or ""),
        ).fetchone()
        if not row and year:
            row = self.conn.execute(
                """
                SELECT * FROM aliases
                WHERE normalized_alias=? AND year='' AND media_type=?
                """,
                (normalized, media_type or ""),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def put_alias(
        self,
        alias: str,
        imdb_id: str,
        year: str = "",
        media_type: str = "",
        source: str = "learned",
        confidence: int | None = None,
    ) -> None:
        normalized = normalize_name(alias)
        iid = normalize_imdb_id(imdb_id)
        if not normalized or not iid:
            return
        # FK requires the entity row. A skeletal row is fine and will later be enriched.
        self.conn.execute(
            "INSERT INTO imdb_entities(imdb_id, checked_at) VALUES(?, '') ON CONFLICT(imdb_id) DO NOTHING",
            (iid,),
        )
        now = utcnow_iso()
        self.conn.execute(
            """
            INSERT INTO aliases (
                normalized_alias, alias, imdb_id, year, media_type, source,
                confidence, created_at, last_seen_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(normalized_alias, year, media_type) DO UPDATE SET
                alias=excluded.alias,
                imdb_id=excluded.imdb_id,
                source=excluded.source,
                confidence=excluded.confidence,
                last_seen_at=excluded.last_seen_at
            """,
            (
                normalized, alias, iid, normalize_year(year), media_type or "", source,
                confidence, now, now,
            ),
        )

    # ------------------------------------------------------------------
    # Migration from v10 JSON caches
    # ------------------------------------------------------------------
    def migrate_v10_json(self, metadata_cache: Path | str | None, imdb_cache: Path | str | None) -> dict[str, int]:
        stats = {"title_rows": 0, "entity_rows": 0, "skipped": 0}

        if metadata_cache:
            path = Path(metadata_cache)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw = {}
                entries = raw.get("entries", raw) if isinstance(raw, dict) else {}
                if isinstance(entries, dict):
                    for key, entry in entries.items():
                        if not isinstance(entry, dict):
                            stats["skipped"] += 1
                            continue
                        parts = str(key).split("|")
                        if len(parts) < 4:
                            stats["skipped"] += 1
                            continue
                        normalized_title, year, media_type, language = parts[0], parts[1], parts[2], "|".join(parts[3:])
                        display = str(entry.get("query_title") or entry.get("title") or normalized_title)
                        # Use the normalized key from JSON verbatim by supplying a title that normalizes equivalently.
                        # If normalization evolved, preserving the display value is still safe; lookups will simply miss
                        # the old row and repopulate it.
                        self.put_title(display, year, media_type, language, entry)
                        stats["title_rows"] += 1

        if imdb_cache:
            path = Path(imdb_cache)
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw = {}
                entities = raw.get("entries", raw) if isinstance(raw, dict) else {}
                if isinstance(entities, dict):
                    for imdb_id, entity in entities.items():
                        if not isinstance(entity, dict) or not normalize_imdb_id(imdb_id):
                            stats["skipped"] += 1
                            continue
                        self.put_imdb_entity(imdb_id, entity)
                        stats["entity_rows"] += 1

        self.conn.commit()
        return stats

    def counts(self) -> dict[str, int]:
        return {
            "titles": int(self.conn.execute("SELECT COUNT(*) FROM title_cache").fetchone()[0]),
            "imdb_entities": int(self.conn.execute("SELECT COUNT(*) FROM imdb_entities").fetchone()[0]),
            "aliases": int(self.conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]),
        }

    def checkpoint(self) -> None:
        self.conn.commit()
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass


def open_metadata_db(root: Path) -> MetadataDB:
    return MetadataDB(root / ".cache" / "metadata" / DEFAULT_DB_NAME)
