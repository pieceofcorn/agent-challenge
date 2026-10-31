from __future__ import annotations

from datetime import datetime, timedelta
import uuid

from .collectors import HttpClient, RSSHubCollector, SourceError, WebPlusCollector
from .config import Config, load_config
from .models import FetchResult, Notice, NoticeContent, SourceResult, convert_notice, iso_utc, utcnow
from .storage import Storage
from .webpages import DirectWebPlusCollector


class PulseService:
    def __init__(self, config: Config, *, storage: Storage | None = None, collectors=None, clock=utcnow,
                 read_only: bool = False):
        self.config = config
        self.read_only = read_only
        self.storage = storage or Storage(config.database, read_only=read_only)
        if not read_only:
            self.storage.sync_sources(config.sources)
        self.clock = clock
        client = HttpClient()
        defaults = {"html": WebPlusCollector(client), "webplus": DirectWebPlusCollector(client)}
        if config.rsshub_base_url is not None:
            defaults["rsshub"] = RSSHubCollector(client, config.rsshub_base_url)
        self.collectors = collectors if collectors is not None else defaults

    @classmethod
    def from_config(cls, path="config.toml", *, read_only=False):
        return cls(load_config(path), read_only=read_only)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.storage.close()

    def _validate_source(self, source_id):
        if source_id is not None and source_id not in {s.id for s in self.config.sources}:
            raise ValueError(f"未知来源标识: {source_id}")

    def fetch_notices(self, *, source_ids: list[str] | None = None) -> FetchResult:
        if self.read_only:
            raise ValueError("只读服务不允许采集或写入")
        if source_ids is not None:
            if not isinstance(source_ids, list) or not all(isinstance(s, str) for s in source_ids):
                raise ValueError("source_ids 必须为字符串列表或 None")
            for source_id in source_ids:
                self._validate_source(source_id)
        selected = [s for s in self.config.sources if (s.enabled if source_ids is None else s.id in source_ids)]
        for source in selected:
            if source.collector not in self.collectors:
                raise ValueError(f"未配置采集器: {source.collector}")
        result = FetchResult(str(uuid.uuid4()), iso_utc(self.clock()))
        self.storage.start_run(result)
        for source in selected:
            now = self.clock()
            row = SourceResult(source.id, "success", iso_utc(now))
            last = self.storage.last_attempt(source.id)
            if last and now < datetime.fromisoformat(last) + timedelta(seconds=source.interval_seconds):
                row.status = "skipped"
                row.error_category = "interval"
                row.error_summary = "尚未达到来源采集间隔"
                converted = []
            else:
                try:
                    items = list(self.collectors[source.collector].collect(source))
                    converted = [convert_notice(item, source.id, source.category, self.clock()) for item in items]
                    row.read = len(items)
                except Exception as exc:
                    row.status = "failed"
                    row.error_category = exc.category if isinstance(exc, SourceError) else "parse_or_adapter"
                    row.error_summary = exc.summary if isinstance(exc, SourceError) else f"采集或模型转换失败: {type(exc).__name__}"
                    converted = []
            # Storage errors propagate; each successful source commits independently.
            with self.storage.connection:
                for identity, notice in converted:
                    outcome = self.storage.upsert(identity, notice)
                    setattr(row, outcome, getattr(row, outcome) + 1)
                row.finished_at = iso_utc(self.clock())
                self.storage.record_source(result.run_id, row)
            result.sources.append(row)
        result.finished_at = iso_utc(self.clock())
        self.storage.finish_run(result)
        return result

    def list_notices(self, *, source_id: str | None = None, since: datetime | None = None,
                     limit: int = 50, offset: int = 0) -> list[Notice]:
        self._validate_source(source_id)
        return self.storage.list(source_id=source_id, since=since, limit=limit, offset=offset)

    def get_notice(self, notice_id: str) -> Notice | None:
        return self.storage.get(notice_id)

    def get_notice_content(self, notice_id: str) -> NoticeContent | None:
        notice = self.get_notice(notice_id)
        return NoticeContent(notice.id, notice.url, notice.content, notice.metadata) if notice else None

    def export_notices(self, *, source_id=None, since=None) -> dict:
        rows, offset = [], 0
        # Keep one read transaction so pagination is consistent with concurrent writers.
        with self.storage.connection:
            self.storage.connection.execute("BEGIN")
            while True:
                page = self.list_notices(source_id=source_id, since=since, limit=500, offset=offset)
                rows.extend(notice.to_dict() for notice in page)
                if len(page) < 500:
                    break
                offset += len(page)
        return {"schema_version": "1", "notices": rows}

    def recent_runs(self, *, limit=50) -> list[dict]:
        return self.storage.recent_runs(limit)
