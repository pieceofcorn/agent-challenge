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
    analyze = commands.add_parser("analyze", help="只读分析已有通知；调用 DeepSeek，不保存分析结果")
    analyze.add_argument("id")
    analyze.add_argument("--preferences", type=Path)
    analyze.add_argument("--env-file", type=Path, default=Path(".env"))
    analyze.add_argument("--as-of", type=aware_datetime)
    args = parser.parse_args(argv)
    try:
        kwargs = {"read_only": True} if args.command == "analyze" else {}
        with PulseService.from_config(args.config, **kwargs) as service:
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
            elif args.command == "analyze":
                output = AnalysisService(service, client=DeepSeekClient(env_file=args.env_file)).analyze_notice(
                    args.id, preferences=load_preferences(args.preferences), as_of=args.as_of)
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
