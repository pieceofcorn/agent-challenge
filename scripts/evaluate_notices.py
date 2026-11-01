"""Run authorized real-notice cases, then score only against reviewed references."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from seu_pulse.analysis_store import AnalysisStore
from seu_pulse.config import load_config
from seu_pulse.evaluation import rule_baseline, score_analysis, score_tools
from seu_pulse.information_agent import InformationAgent
from seu_pulse.model_client import DeepSeekClient
from seu_pulse.models import iso_utc, utcnow
from seu_pulse.service import PulseService


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def run(args):
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    samples = bundle["samples"]
    if not 10 <= len(samples) <= 15 or len({r["notice_id"] for r in samples}) != len(samples):
        raise ValueError("需要 10..15 条不同的获准真实通知")
    if args.output.exists():
        raise ValueError("输出目录已存在，请使用新路径保留历史")
    config = load_config(args.config)
    before = hashlib.sha256(config.database.read_bytes()).hexdigest()
    # Freeze approved SQLite versions before any API call. These are real records, never fixtures.
    rows = {}
    with PulseService(config, read_only=True) as service:
        for sample in samples:
            notice = service.get_notice(sample["notice_id"])
            if notice is None or notice.content_hash != sample["source_content_hash"]:
                raise ValueError("候选通知缺失或已变化，未发起模型请求")
            rows[notice.id] = notice

    class FrozenNotices:
        def get_notice(self, notice_id):
            return deepcopy(rows.get(notice_id))

    as_of = datetime.fromisoformat(bundle["as_of"].replace("Z", "+00:00"))
    iso_utc(as_of)
    args.output.mkdir(parents=True)
    write_new(args.output / "plan.json", {"schema_version": "1", "manifest_hash": bundle["manifest_hash"],
        "as_of": iso_utc(as_of), "notice_ids": list(rows), "preferences": None,
        "input_mode": "frozen real SQLite records; body hidden until requested", "human_reference_status": "unscored"})
    analyzer = InformationAgent(FrozenNotices(), client=DeepSeekClient(env_file=args.env_file))
    cases, consecutive, previous_error = [], 0, None
    with AnalysisStore(args.output / "analyses.db") as store:
        for index, notice_id in enumerate(rows):
            result = analyzer.analyze_notice(notice_id, as_of=as_of)
            context = analyzer.input_snapshot
            record = store.save(result, input_snapshot=context, source_snapshot=analyzer.source_snapshot)
            baseline = rule_baseline(context) if context is not None else None
            case = {"notice_id": notice_id, "source_content_hash": rows[notice_id].content_hash,
                    "attempt_id": record.attempt_id, "result": result, "input_snapshot": context,
                    "baseline": baseline, "baseline_input_hash": result["input_hash"],
                    "raw_outputs_unvalidated": list(analyzer.client.last_outputs), "scores": None}
            name = f"case-{index + 1:02d}.json"
            write_new(args.output / name, case)
            cases.append({"file": name, "notice_id": notice_id, "status": result["status"],
                          "model_requests": result["model_requests"], "error": result["error"]})
            print(json.dumps({"case": index + 1, "status": result["status"],
                              "model_requests": result["model_requests"]}), flush=True)
            code = result["error"]["code"] if result["error"] else None
            consecutive = consecutive + 1 if code and code == previous_error else (1 if code else 0)
            previous_error = code
            if consecutive >= 3:
                break
    after = hashlib.sha256(config.database.read_bytes()).hexdigest()
    summary = {"schema_version": "1", "completed_at": iso_utc(utcnow()),
               "manifest_hash": bundle["manifest_hash"], "as_of": iso_utc(as_of),
               "requested_samples": len(samples), "completed_samples": len(cases),
               "stopped_after_three_same_errors": consecutive >= 3,
               "database_sha256_before": before, "database_sha256_after": after,
               "database_unchanged": before == after, "cases": cases, "accuracy": None,
               "reference_status": "no human scoring yet; API validity is not semantic correctness"}
    write_new(args.output / "summary.json", summary)
    return 0 if before == after and len(cases) == len(samples) and all(c["status"] != "failed" for c in cases) else 1


def score(args):
    references = json.loads(args.references.read_text(encoding="utf-8"))
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    if references["manifest_hash"] != summary["manifest_hash"]:
        raise ValueError("参考与评估样本不匹配")
    by_id = {r["notice_id"]: r for r in references["samples"]}
    results = []
    totals = {"agent": {}, "baseline": {}}
    tool_totals = {}
    for row in summary["cases"]:
        case = json.loads((args.run_dir / row["file"]).read_text(encoding="utf-8"))
        reference = by_id[case["notice_id"]]
        if reference["source_content_hash"] != case["source_content_hash"]:
            raise ValueError("参考内容版本不匹配")
        values = {"notice_id": case["notice_id"], "agent": score_analysis(case["result"]["analysis"], reference),
                  "baseline": score_analysis(case["baseline"], reference),
                  "tools": score_tools(case["result"]["agent_trace"], reference)}
        results.append(values)
        for method in totals:
            for field, correct in values[method]["fields"].items():
                counts = totals[method].setdefault(field, {"correct": 0, "scored": 0})
                counts["scored"] += 1
                counts["correct"] += int(correct)
        for field, value in values["tools"].items():
            if value is not None:
                counts = tool_totals.setdefault(field, {"correct": 0, "scored": 0})
                counts["scored"] += 1
                counts["correct"] += int(value)
    write_new(args.output, {"schema_version": "1", "manifest_hash": summary["manifest_hash"],
                           "cases": results, "per_field_totals": totals, "tool_totals": tool_totals,
                           "scope": "Only explicitly reviewed fields scored; unlabelled fields remain unscored"})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    live = commands.add_parser("run", help="仅在具体通知外发获准后运行真实模型")
    live.add_argument("--config", default="config.toml")
    live.add_argument("--env-file", default=".env")
    live.add_argument("--bundle", type=Path, required=True)
    live.add_argument("--output", type=Path, required=True)
    scoring = commands.add_parser("score", help="不调用模型，只对已人工签审参考评分")
    scoring.add_argument("--run-dir", type=Path, required=True)
    scoring.add_argument("--references", type=Path, required=True)
    scoring.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args) if args.command == "run" else score(args)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"评估配置或文件错误: {type(exc).__name__}\n")


if __name__ == "__main__":
    raise SystemExit(main())
