"""Prepare real local samples and empty human-reference forms; never calls an API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from seu_pulse.analysis import compute_urgency
from seu_pulse.evaluation import rule_baseline
from seu_pulse.models import digest
from seu_pulse.service import PulseService
from seu_pulse.cli import aware_datetime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=aware_datetime, default=aware_datetime("2026-11-01T00:00:00Z"))
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("请使用新输出目录以保留历史材料")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows = manifest["samples"]
    if not 10 <= len(rows) <= 15 or len({r["notice_id"] for r in rows}) != len(rows):
        parser.error("需要 10..15 条互不重复的真实通知")
    samples, references = [], []
    with PulseService.from_config(args.config, read_only=True) as service:
        for row in rows:
            notice = service.get_notice(row["notice_id"])
            if notice is None or notice.content_hash != row["content_hash"]:
                parser.error("通知缺失或内容已变，请重新审查清单")
            snapshot = {key: getattr(notice, key) for key in (
                "id", "source_id", "title", "url", "published_at", "summary", "content", "category")}
            context = {"notice": snapshot, "preferences": None}
            baseline = rule_baseline(context)
            samples.append({"notice_id": notice.id, "source_content_hash": notice.content_hash,
                            "input_snapshot": context, "baseline_preview": baseline,
                            "urgency_preview": compute_urgency(baseline["registration_deadlines"], args.as_of)})
            references.append({"notice_id": notice.id, "source_content_hash": notice.content_hash,
                "source_url": notice.url, "review_status": "draft", "reviewer": None,
                "accepted_values": {field + ".value": [] for field in ("category", "importance", "relevance", "action_required")},
                "must_be_unknown": ["relevance.value"], "evidence_notes": [],
                "allowed_tools": None, "required_tools": None, "time_reference_status": "unreviewed"})
    args.output.mkdir(parents=True)
    bundle = {"schema_version": "1", "manifest_hash": digest(manifest), "as_of": args.as_of.isoformat(),
              "preferences": None, "reference_status": "draft_unreviewed", "samples": samples,
              "scope": "Local real-notice preparation only; baseline preview is not human reference"}
    (args.output / "samples.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "references.draft.json").write_text(json.dumps({"schema_version": "1",
        "manifest_hash": digest(manifest), "samples": references}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "samples": len(samples), "api_requests": 0,
                      "human_reviewed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
