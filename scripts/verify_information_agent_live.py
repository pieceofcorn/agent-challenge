"""Task 2.2 live protocol evidence; synthetic or explicitly selected existing notices."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import tempfile

from seu_pulse.agent_tools import AgentLimits
from seu_pulse.config import load_config
from seu_pulse.information_agent import InformationAgent
from seu_pulse.model_client import DeepSeekClient
from seu_pulse.models import iso_utc, utcnow
from seu_pulse.service import PulseService
from scripts.verify_analysis_live import SyntheticNotices


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--env-file", default=".env")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--synthetic", action="store_true")
    inputs.add_argument("--notice-id", action="append")
    parser.add_argument("--initial-detail", action="store_true")
    parser.add_argument("--fixture-preferences", action="store_true",
                        help="仅合成模式：手写测试偏好，不代表用户背景")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.notice_id and not 1 <= len(args.notice_id) <= 3:
        parser.error("只接受 1..3 个已获外发授权的通知 ID")
    if args.fixture_preferences and not args.synthetic:
        parser.error("手写偏好只允许用于合成通知验证")
    if args.output.exists():
        parser.error("输出已存在，请指定新路径保留证据")
    as_of = utcnow()
    if args.synthetic:
        fixture = SyntheticNotices(as_of)
        opened, ids, before = nullcontext(fixture), list(fixture.rows), None
    else:
        config = load_config(args.config)
        before = hashlib.sha256(config.database.read_bytes()).hexdigest()
        opened, ids = PulseService(config, read_only=True), args.notice_id
    client = DeepSeekClient(env_file=args.env_file)
    results, sources, raw_outputs = [], [], []
    with tempfile.TemporaryDirectory(prefix="seu-pulse-fixture-") as temp, opened as notices:
        preferences_path = None
        if args.fixture_preferences:
            preferences_path = Path(temp) / "synthetic-preferences.json"
            preferences_path.write_text(json.dumps({"interests": ["科研讲座"], "keywords": [],
                                                    "focus_areas": []}, ensure_ascii=False), encoding="utf-8")
        agent = InformationAgent(notices, client=client)
        for notice_id in ids:
            notice = notices.get_notice(notice_id)
            sources.append(None if notice is None else {
                "notice_id": notice.id, "source_id": notice.source_id, "url": notice.url,
                "has_content": bool(notice.content), "content_chars": len(notice.content or ""),
                "content_hash": notice.content_hash})
            results.append(agent.analyze_notice(notice_id, as_of=as_of,
                           preferences_path=preferences_path, initial_detail=args.initial_detail,
                           limits=AgentLimits()))
            raw_outputs.append(list(client.last_outputs))
    after = None if args.synthetic else hashlib.sha256(config.database.read_bytes()).hexdigest()
    report = {"mode": "synthetic_input_live_model" if args.synthetic else "existing_notices_live_model",
              "verified_at": iso_utc(utcnow()), "as_of": iso_utc(as_of),
              "initial_detail": args.initial_detail, "synthetic_preferences": args.fixture_preferences,
              "framework": client.framework, "framework_version": client.framework_version,
              "database_unchanged": None if args.synthetic else before == after,
              "database_sha256_before": before, "database_sha256_after": after,
              "sources": sources, "results": results, "raw_outputs_unvalidated": raw_outputs,
              "scope": "Task 2.2 tool loop smoke check; not task 2.3 evaluation or persistence"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "database_unchanged": report["database_unchanged"],
                      "statuses": [r["status"] for r in results],
                      "errors": [r["error"] for r in results],
                      "model_requests": [r["model_requests"] for r in results],
                      "tools": [[(c["tool"], c["status"], c["feedback_request"])
                                 for c in r["agent_trace"]["tool_calls"]] for r in results]}, ensure_ascii=False))
    return 0 if before == after and all(r["status"] != "failed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
