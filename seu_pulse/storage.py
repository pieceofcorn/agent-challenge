from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from .config import SourceConfig
from .models import FetchResult, Notice, SourceResult, iso_utc, notice_hash


class Storage:
    def __init__(self, path: str | Path, *, read_only: bool = False):
        if read_only:
            self.connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro",
                                              uri=True, timeout=10)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            return
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, config_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notices (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                identity TEXT NOT NULL, title TEXT NOT NULL, url TEXT, published_at TEXT,
                first_seen_at TEXT NOT NULL, fetched_at TEXT NOT NULL,
                summary TEXT, content TEXT, category TEXT NOT NULL,
                content_hash TEXT NOT NULL, metadata TEXT NOT NULL,
                UNIQUE(source_id, identity)
            );
            CREATE INDEX IF NOT EXISTS notices_recent ON notices(fetched_at DESC, id ASC);
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS source_runs (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                source_id TEXT NOT NULL REFERENCES sources(id),
                status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                read INTEGER NOT NULL, inserted INTEGER NOT NULL, updated INTEGER NOT NULL,
                unchanged INTEGER NOT NULL, error_category TEXT, error_summary TEXT,
                PRIMARY KEY(run_id, source_id)
            );
        """)

    def close(self):
        self.connection.close()

    def sync_sources(self, sources: tuple[SourceConfig, ...]):
        with self.connection:
            self.connection.executemany(
                "INSERT INTO sources VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json",
                [(s.id, json.dumps(asdict(s), ensure_ascii=False)) for s in sources])

    @staticmethod
    def _notice(row) -> Notice | None:
        if row is None:
            return None
        value = dict(row)
        value.pop("identity", None)
        value["metadata"] = json.loads(value["metadata"])
        return Notice(**value)

    def upsert(self, identity: str, notice: Notice) -> str:
        old = self.get(notice.id)
        outcome = "inserted"
        if old:
            notice.first_seen_at = old.first_seen_at
            for key in ("url", "published_at", "summary", "content"):
                if getattr(notice, key) is None:
                    setattr(notice, key, getattr(old, key))
            notice.metadata = {**old.metadata, **notice.metadata}
            # Seeing an item again must never move its fetch timestamp backwards.
            notice.fetched_at = max(notice.fetched_at, old.fetched_at)
            notice.content_hash = notice_hash(notice)
            outcome = "unchanged" if old.content_hash == notice.content_hash else "updated"
        value = asdict(notice)
        value["identity"] = identity
        value["metadata"] = json.dumps(notice.metadata, ensure_ascii=False, sort_keys=True, allow_nan=False)
        columns = list(value)
        updates = ",".join(f"{key}=excluded.{key}" for key in columns if key not in {"id", "first_seen_at", "identity", "source_id"})
        self.connection.execute(
            f"INSERT INTO notices ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
            f"ON CONFLICT(source_id,identity) DO UPDATE SET {updates}", list(value.values()))
        return outcome

    def get(self, notice_id: str) -> Notice | None:
        return self._notice(self.connection.execute("SELECT * FROM notices WHERE id=?", (notice_id,)).fetchone())

    def list(self, *, source_id=None, since: datetime | None = None, limit=50, offset=0) -> list[Notice]:
        if type(limit) is not int or type(offset) is not int or limit < 1 or offset < 0:
            raise ValueError("limit 必须为正整数，offset 必须为非负整数")
        conditions, args = [], []
        if source_id is not None:
            conditions.append("source_id=?")
            args.append(source_id)
        if since is not None:
            conditions.append("fetched_at>=?")
            args.append(iso_utc(since))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.connection.execute(
            "SELECT * FROM notices" + where + " ORDER BY fetched_at DESC, id ASC LIMIT ? OFFSET ?",
            [*args, limit, offset])
        return [self._notice(row) for row in rows]

    def start_run(self, result: FetchResult):
        with self.connection:
            self.connection.execute("INSERT INTO runs VALUES (?, ?, NULL)", (result.run_id, result.started_at))

    def finish_run(self, result: FetchResult):
        with self.connection:
            self.connection.execute("UPDATE runs SET finished_at=? WHERE run_id=?", (result.finished_at, result.run_id))

    def record_source(self, run_id: str, result: SourceResult):
        values = {"run_id": run_id, **asdict(result)}
        self.connection.execute(
            f"INSERT INTO source_runs ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
            list(values.values()))

    def last_attempt(self, source_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT started_at FROM source_runs WHERE source_id=? AND status IN ('success','failed') "
            "ORDER BY started_at DESC LIMIT 1", (source_id,)).fetchone()
        return row[0] if row else None

    def recent_runs(self, limit=50) -> list[dict]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit 必须为正整数")
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM source_runs ORDER BY started_at DESC, run_id ASC, source_id ASC LIMIT ?", (limit,))]
