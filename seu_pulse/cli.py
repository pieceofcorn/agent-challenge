from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

from .config import ConfigError
from .models import iso_utc
from .service import PulseService
from .analysis import AnalysisService, load_preferences
from .model_client import DeepSeekClient
from .information_agent import InformationAgent
from .agent_tools import AgentLimits
from .analysis_store import AnalysisStore


def aware_datetime(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        iso_utc(parsed)
        return parsed
    except ValueError as exc:
        raise argparse.ArgumentTypeError("时间必须为带时区的 ISO 8601 格式") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="seu-pulse", description="东南大学公开通知采集与查询")
    parser.add_argument("--config", default="config.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="单次采集；仍遵守来源间隔")
    fetch.add_argument("--source", action="append", dest="source_ids")
    recent = commands.add_parser("list", help="最近通知，输出通知模型 JSON 数组")
    recent.add_argument("--source", dest="source_id")
    recent.add_argument("--since", type=aware_datetime)
    recent.add_argument("--limit", type=int, default=50)
    recent.add_argument("--offset", type=int, default=0)
    get = commands.add_parser("get", help="按稳定 ID 查看通知")
    get.add_argument("id")
    get.add_argument("--content-only", action="store_true")
    export = commands.add_parser("export", help="导出所有匹配通知")
    export.add_argument("--source", dest="source_id")
    export.add_argument("--since", type=aware_datetime)
    export.add_argument("--output", type=Path)
    runs = commands.add_parser("runs", help="最近逐源运行记录")
    runs.add_argument("--limit", type=int, default=50)
    analyze = commands.add_parser("analyze", help="只读分析已有通知；调用 DeepSeek，默认不保存结果")
    analyze.add_argument("id")
    analyze.add_argument("--preferences", type=Path)
    analyze.add_argument("--env-file", type=Path, default=Path(".env"))
    analyze.add_argument("--as-of", type=aware_datetime)
    analyze.add_argument("--save", action="store_true")
    analyze.add_argument("--analysis-db", type=Path, default=Path("data/notice-analyses.db"))
    agent = commands.add_parser("agent-analyze", help="单 Agent 按需调用只读工具；默认不保存结果")
    agent.add_argument("id")
    agent.add_argument("--preferences", type=Path)
    agent.add_argument("--env-file", type=Path, default=Path(".env"))
    agent.add_argument("--as-of", type=aware_datetime)
    agent.add_argument("--initial-detail", action="store_true")
    agent.add_argument("--initial-preferences", action="store_true")
    agent.add_argument("--max-requests", type=int, default=6)
    agent.add_argument("--max-tool-calls", type=int, default=4)
    agent.add_argument("--request-timeout", type=float, default=60)
    agent.add_argument("--tool-timeout", type=float, default=5)
    agent.add_argument("--run-timeout", type=float, default=180)
    agent.add_argument("--save", action="store_true")
    agent.add_argument("--analysis-db", type=Path, default=Path("data/notice-analyses.db"))
    analyses = commands.add_parser("analysis-list", help="只读查询分析记录，默认排除失败尝试")
    analyses.add_argument("--analysis-db", type=Path, default=Path("data/notice-analyses.db"))
    analyses.add_argument("--notice-id")
    analyses.add_argument("--include-failed", action="store_true")
    analyses.add_argument("--limit", type=int, default=50)
    analysis_get = commands.add_parser("analysis-get", help="只读查看一次分析或失败尝试及输入快照")
    analysis_get.add_argument("id")
    analysis_get.add_argument("--analysis-db", type=Path, default=Path("data/notice-analyses.db"))
    args = parser.parse_args(argv)
    try:
        if args.command in {"analysis-list", "analysis-get"}:
            with AnalysisStore(args.analysis_db, read_only=True) as store:
                if args.command == "analysis-list":
                    output = [record.to_dict() for record in store.list_records(
                        notice_id=args.notice_id, include_failed=args.include_failed, limit=args.limit)]
                else:
                    record = store.get(args.id)
                    output = record.to_dict() if record else None
            print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
            return 3 if output is None else 0
        limits = (AgentLimits(args.max_requests, args.max_tool_calls, args.request_timeout,
                              args.tool_timeout, args.run_timeout) if args.command == "agent-analyze" else None)
        kwargs = {"read_only": True} if args.command in {"analyze", "agent-analyze"} else {}
        with PulseService.from_config(args.config, **kwargs) as service:
            if args.command in {"analyze", "agent-analyze"} and args.save:
                if args.analysis_db.resolve() == service.config.database.resolve():
                    raise ValueError("分析库不能指向原通知数据库")
            code = 0
            if args.command == "fetch":
                result = service.fetch_notices(source_ids=args.source_ids)
                output = result.to_dict()
                code = 1 if output["totals"]["failed_sources"] else 0
            elif args.command == "list":
                output = [n.to_dict() for n in service.list_notices(source_id=args.source_id, since=args.since,
                                                                  limit=args.limit, offset=args.offset)]
            elif args.command == "get":
                notice = service.get_notice_content(args.id) if args.content_only else service.get_notice(args.id)
                output = asdict(notice) if notice else None
                code = 3 if notice is None else 0
            elif args.command == "export":
                output = service.export_notices(source_id=args.source_id, since=args.since)
            elif args.command in {"analyze", "agent-analyze"}:
                client = DeepSeekClient(env_file=args.env_file)
                if args.command == "analyze":
                    analyzer = AnalysisService(service, client=client)
                    output = analyzer.analyze_notice(
                        args.id, preferences=load_preferences(args.preferences), as_of=args.as_of)
                else:
                    analyzer = InformationAgent(service, client=client)
                    output = analyzer.analyze_notice(
                        args.id, preferences_path=args.preferences, initial_detail=args.initial_detail,
                        initial_preferences=args.initial_preferences, limits=limits, as_of=args.as_of)
                if args.save:
                    with AnalysisStore(args.analysis_db) as store:
                        record = store.save(output, input_snapshot=analyzer.input_snapshot,
                                            source_snapshot=analyzer.source_snapshot)
                    output["storage"] = {"attempt_id": record.attempt_id, "analysis_id": record.analysis_id,
                                         "status": record.result["status"]}
                code = (3 if output["error"] and output["error"]["code"] == "notice_not_found"
                        else 1 if output["status"] == "failed" else 4
                        if output["status"] == "insufficient_information" else 0)
            else:
                output = service.recent_runs(limit=args.limit)
            serialized = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            if args.command == "export" and args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(serialized, encoding="utf-8")
            else:
                print(serialized, end="")
            return code
    except (ConfigError, ValueError) as exc:
        print(f"参数或配置错误: {exc}", file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError) as exc:
        print(f"服务级存储或文件错误: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
