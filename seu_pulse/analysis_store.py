"""Append-only local analysis records, separate from the read-only notice database."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import uuid

from .analysis import compute_urgency, validate_preferences
from .analysis_models import strict_json, validate_analysis
from .models import digest, iso_utc, utcnow


@dataclass(frozen=True)
class AnalysisAttempt:
    attempt_id: str
    stored_at: str
    input_snapshot: dict | None
    source_snapshot: dict | None
    result: dict
    record_schema_version: str = "1"
    analysis_id: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class NoticeAnalysis(AnalysisAttempt):
    """Only validated success or explicitly partial records may use this object."""


SOURCE_FIELDS = {"id", "source_id", "title", "url", "published_at", "summary", "content", "category", "content_hash"}


def validate_record(result, input_snapshot, source_snapshot):
    """Validate again at the persistence boundary; no implicit model-output repairs."""
    result, context, source = deepcopy((result, input_snapshot, source_snapshot))
    # Reject NaN, non-JSON values and duplicate serialized keys before writing anything.
    json.dumps([result, context, source], ensure_ascii=False, allow_nan=False)
    if (not isinstance(result, dict) or result.get("status") not in {"success", "insufficient_information", "failed"}
            or result.get("analysis_schema_version") != "1" or not isinstance(result.get("notice_id"), str)
            or not result["notice_id"].strip()):
        raise ValueError("无效分析封装")
    for name in ("analyzed_at", "as_of"):
        if not isinstance(result.get(name), str):
            raise ValueError("缺少分析时间")
        value = datetime.fromisoformat(result[name].replace("Z", "+00:00"))
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("分析时间必须为 UTC")
    if source is not None:
        if not isinstance(source, dict) or set(source) != SOURCE_FIELDS or source["id"] != result["notice_id"]:
            raise ValueError("原通知快照不匹配")
        original_hash = digest([source[k] for k in ("title", "url", "published_at", "summary", "content", "category")])
        if source["content_hash"] != original_hash or result.get("notice_content_hash") != original_hash:
            raise ValueError("原通知指纹不匹配")
    elif result.get("notice_content_hash") is not None:
        raise ValueError("缺少原通知快照")
    if context is not None:
        if not isinstance(context, dict) or set(context) != {"notice", "preferences"} or source is None:
            raise ValueError("输入快照结构无效")
        if not isinstance(context.get("notice"), dict) or set(context["notice"]) != SOURCE_FIELDS - {"content_hash"}:
            raise ValueError("输入通知字段无效")
        for name, value in context["notice"].items():
            if value != source[name] and not (name == "content" and value is None):
                raise ValueError("实际输入与原通知快照不匹配")
        validate_preferences(context["preferences"])
        if result.get("input_hash") != digest(context) or result.get("preferences_hash") != digest(context["preferences"]):
            raise ValueError("输入或偏好指纹不匹配")
    elif result.get("input_hash") is not None:
        raise ValueError("缺少输入快照")
    model = result.get("model_info")
    if not isinstance(model, dict) or set(model) != {"provider", "requested_model", "returned_model", "model_version", "request_id"}:
        raise ValueError("缺少实际模型信息")
    if any(value is not None and not isinstance(value, str) for value in model.values()):
        raise ValueError("模型信息类型无效")
    if any(not model.get(name) for name in ("provider", "requested_model")):
        raise ValueError("缺少请求模型信息")
    if (not isinstance(result.get("prompt_hash"), str) or len(result["prompt_hash"]) != 64
            or any(c not in "0123456789abcdef" for c in result["prompt_hash"])):
        raise ValueError("缺少提示指纹")
    if result["status"] == "failed":
        error = result.get("error")
        if (result.get("analysis") is not None or result.get("urgency") is not None
                or not isinstance(error, dict) or set(error) != {"code", "message"}
                or not all(isinstance(v, str) and v.strip() for v in error.values())):
            raise ValueError("失败尝试不能包含有效分析")
    else:
        if context is None or result.get("error") is not None:
            raise ValueError("有效分析必须关联输入，且不能含执行错误")
        analysis = validate_analysis(result.get("analysis"), context)
        as_of = datetime.fromisoformat(result["as_of"].replace("Z", "+00:00"))
        if result.get("urgency") != compute_urgency(analysis["registration_deadlines"], as_of):
            raise ValueError("程序紧迫性不匹配")
        if result["status"] == "success" and not context["notice"]["content"]:
            raise ValueError("无正文的结果不能伪装为成功")
    return result, context, source


class AnalysisStore:
    def __init__(self, path, *, read_only=False, clock=utcnow):
        self.read_only, self.clock = read_only, clock
        path = Path(path)
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
        uri = path.resolve().as_uri() + ("?mode=ro" if read_only else "?mode=rwc")
        self.connection = sqlite3.connect(uri, uri=True, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        try:
            tables = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"analysis_store_metadata", "analysis_attempts", "notice_analyses"}:
                raise ValueError("目标不是独立分析数据库，拒绝修改")
            if tables:
                version = self.connection.execute("SELECT version FROM analysis_store_metadata").fetchall()
                if [r[0] for r in version] != ["1"]:
                    raise ValueError("不支持的分析库版本")
            elif read_only:
                raise ValueError("目标不是有效分析数据库")
            else:
                self.connection.executescript("""
                    BEGIN;
                    CREATE TABLE analysis_store_metadata(version TEXT PRIMARY KEY);
                    INSERT INTO analysis_store_metadata VALUES ('1');
                    CREATE TABLE analysis_attempts(
                        attempt_id TEXT PRIMARY KEY, notice_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('success','insufficient_information','failed')),
                        analyzed_at TEXT NOT NULL, stored_at TEXT NOT NULL,
                        result_json TEXT NOT NULL, input_json TEXT, source_json TEXT,
                        UNIQUE(attempt_id,status));
                    CREATE TABLE notice_analyses(
                        analysis_id TEXT PRIMARY KEY, notice_id TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('success','insufficient_information')),
                        notice_content_hash TEXT NOT NULL, input_hash TEXT NOT NULL,
                        preferences_hash TEXT NOT NULL, prompt_hash TEXT NOT NULL,
                        provider TEXT, requested_model TEXT, returned_model TEXT, model_version TEXT,
                        as_of TEXT NOT NULL,
                        FOREIGN KEY(analysis_id,status) REFERENCES analysis_attempts(attempt_id,status));
                    CREATE INDEX analyses_notice_version ON notice_analyses(notice_id,notice_content_hash);
                    CREATE INDEX attempts_notice_time ON analysis_attempts(notice_id,analyzed_at);
                    COMMIT;
                """)
        except Exception:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def save(self, result, *, input_snapshot, source_snapshot):
        if self.read_only:
            raise ValueError("只读分析库不能保存")
        result, context, source = validate_record(result, input_snapshot, source_snapshot)
        attempt_id, stored_at = uuid.uuid4().hex, iso_utc(self.clock())
        serialize = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) if value is not None else None
        with self.connection:
            self.connection.execute("INSERT INTO analysis_attempts VALUES (?,?,?,?,?,?,?,?)", (
                attempt_id, result["notice_id"], result["status"], result["analyzed_at"], stored_at,
                serialize(result), serialize(context), serialize(source)))
            if result["status"] != "failed":
                model = result["model_info"]
                self.connection.execute("INSERT INTO notice_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                    attempt_id, result["notice_id"], result["status"], result["notice_content_hash"],
                    result["input_hash"], result["preferences_hash"], result["prompt_hash"],
                    model["provider"], model["requested_model"], model["returned_model"], model["model_version"], result["as_of"]))
        return self.get(attempt_id)

    def _record(self, row):
        if row is None:
            return None
        result = strict_json(row["result_json"])
        context = strict_json(row["input_json"]) if row["input_json"] is not None else None
        source = strict_json(row["source_json"]) if row["source_json"] is not None else None
        result, context, source = validate_record(result, context, source)
        valid = result["status"] != "failed"
        if any(row[k] != result[k] for k in ("notice_id", "status", "analyzed_at")):
            raise ValueError("分析记录索引与封装不一致")
        link = self.connection.execute("SELECT * FROM notice_analyses WHERE analysis_id=?", (row["attempt_id"],)).fetchone()
        if bool(link) != valid:
            raise ValueError("有效分析关联不一致")
        if valid:
            expected = {k: result[k] for k in ("notice_id", "status", "notice_content_hash", "input_hash",
                                              "preferences_hash", "prompt_hash", "as_of")}
            expected.update({k: result["model_info"][k] for k in ("provider", "requested_model", "returned_model", "model_version")})
            if any(link[k] != value for k, value in expected.items()):
                raise ValueError("分析版本索引与封装不一致")
        cls = NoticeAnalysis if valid else AnalysisAttempt
        return cls(row["attempt_id"], row["stored_at"], context, source, result,
                   analysis_id=row["attempt_id"] if valid else None)

    def get(self, attempt_id):
        return self._record(self.connection.execute(
            "SELECT * FROM analysis_attempts WHERE attempt_id=?", (attempt_id,)).fetchone())

    def list_records(self, *, notice_id=None, include_failed=False, limit=50):
        if type(limit) is not int or limit < 1 or type(include_failed) is not bool:
            raise ValueError("limit 须为正整数，include_failed 须为布尔值")
        conditions, params = [], []
        if not include_failed:
            conditions.append("status != 'failed'")
        if notice_id is not None:
            conditions.append("notice_id=?")
            params.append(notice_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return [self._record(row) for row in self.connection.execute(
            "SELECT * FROM analysis_attempts" + where + " ORDER BY analyzed_at DESC,attempt_id ASC LIMIT ?",
            [*params, limit])]
