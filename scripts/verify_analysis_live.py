"""Small, explicit live-model smoke check; not the task 2.3 evaluation."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from seu_pulse.analysis import AnalysisService, load_preferences
from seu_pulse.config import load_config
from seu_pulse.model_client import DeepSeekClient
from seu_pulse.models import CollectedNotice, convert_notice, iso_utc, notice_hash, utcnow
from seu_pulse.service import PulseService


class SyntheticNotices:
    """Handwritten test input, never populated from campus or user data."""

    def __init__(self, now):
        _, full = convert_notice(CollectedNotice(
            "SYNTHETIC API TEST 科研讲座",
            url="https://example.test/synthetic-api-test",
            content=("合成通知，仅用于接口测试，不代表真实活动。线上科研讲座，"
                     "活动时间2026年11月5日14:00 UTC；报名截止2026年11月3日12:00 UTC。地点为线上。")
        ), "synthetic-test", "synthetic", now)
        missing = replace(full, id="synthetic-missing-body", title="SYNTHETIC API TEST 活动通知",
                          content=None)
        missing.content_hash = notice_hash(missing)
        self.rows = {full.id: full, missing.id: missing}

    def get_notice(self, notice_id):
        return self.rows.get(notice_id)


class RecordingClient:
    """Local diagnostic output only; never records authentication headers or reasoning."""

    def __init__(self, client):
        self.client = client
        self.provider, self.model = client.provider, client.model
        self.outputs = []

    def complete(self, messages):
        result = self.client.complete(messages)
        self.outputs.append({"model": result.model, "request_id": result.request_id,
                             "content": result.content})
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--env-file", default=".env")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--notice-id", action="append")
    inputs.add_argument("--synthetic", action="store_true",
                        help="仅发送手写合成文本；不读取校园通知、数据库或用户偏好")
    parser.add_argument("--preferences", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.notice_id and not 1 <= len(args.notice_id) <= 3:
        parser.error("接口烟雾检查每次只接受 1..3 个真实通知 ID")
    if args.synthetic and args.preferences:
        parser.error("合成接口验证不读取用户偏好")
    if args.output.exists():
        parser.error("输出文件已存在，请指定新路径以保留历史证据")
    as_of = utcnow()
    if args.synthetic:
        fixture = SyntheticNotices(as_of)
        opened = nullcontext(fixture)
        notice_ids = list(fixture.rows)
        before = None
    else:
        config = load_config(args.config)
        before = hashlib.sha256(config.database.read_bytes()).hexdigest()
        opened = PulseService(config, read_only=True)
        notice_ids = args.notice_id
    results, sources = [], []
    client = RecordingClient(DeepSeekClient(env_file=args.env_file))
    with opened as service:
        analyzer = AnalysisService(service, client=client)
        for notice_id in notice_ids:
            notice = service.get_notice(notice_id)
            sources.append(None if notice is None else {
                "notice_id": notice.id, "source_id": notice.source_id, "url": notice.url,
                "has_content": bool(notice.content), "content_chars": len(notice.content or ""),
                "content_hash": notice.content_hash})
            results.append(analyzer.analyze_notice(notice_id, preferences=load_preferences(args.preferences),
                                                  as_of=as_of))
    after = None if args.synthetic else hashlib.sha256(config.database.read_bytes()).hexdigest()
    report = {
        "mode": "live_model_synthetic_input" if args.synthetic else "live_model_existing_notices_no_fixtures",
        "verified_at": iso_utc(utcnow()),
        "provider": "deepseek", "requested_model": "deepseek-flash", "as_of": iso_utc(as_of),
        "database_unchanged": None if args.synthetic else before == after, "database_sha256_before": before,
        "database_sha256_after": after, "sources": sources, "results": results,
        "raw_outputs_unvalidated": client.outputs,
        "scope": "Task 2.1 API smoke check only; not task 2.2 tool calling or task 2.3 evaluation",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "output": str(args.output), "database_unchanged": report["database_unchanged"],
        "statuses": [r["status"] for r in results],
        "error_codes": [r["error"]["code"] if r["error"] else None for r in results],
        "model_requests": sum(r["model_requests"] for r in results),
        "returned_models": [r["model_info"]["returned_model"] for r in results],
    }, ensure_ascii=False))
    return 0 if before == after and all(r["status"] != "failed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
