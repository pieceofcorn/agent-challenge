"""Separate live-source acceptance check. Never imports test fixtures or mocks."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from seu_pulse.config import load_config
from seu_pulse.models import iso_utc, utcnow
from seu_pulse.service import PulseService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--source", action="append", dest="source_ids")
    parser.add_argument("--database", type=Path, default=Path("data/live-verification.db"))
    parser.add_argument("--output", type=Path, default=Path("data/live-verification.json"))
    args = parser.parse_args()
    config = load_config(args.config)
    known = {s.id for s in config.sources}
    if args.source_ids is not None and set(args.source_ids) - known:
        parser.error("包含未配置的来源标识")
    # A dedicated verification database and zero scheduled interval allow an immediate second pass.
    # Per-request pacing, robots rules, timeout and bounded retries remain active.
    config = replace(config, database=args.database,
                     sources=tuple(replace(s, interval_seconds=0) for s in config.sources))
    with PulseService(config) as service:
        selected = args.source_ids if args.source_ids is not None else [s.id for s in config.sources if s.enabled]
        if not selected:
            parser.error("没有已启用或已选择的来源")
        first = service.fetch_notices(source_ids=selected)
        before = service.export_notices()["notices"]
        second = service.fetch_notices(source_ids=selected)
        after = service.export_notices()["notices"]
        successful = {s.source_id for s in first.sources if s.status == "success" and s.read > 0}
        repeated = {s.source_id for s in second.sources if s.status == "success" and s.read > 0}
        queried = service.list_notices(limit=3)
        query_verified = bool(queried) and all(service.get_notice(n.id) == n for n in queried)
        # Only assess repetition where both live requests actually returned notices.
        stable_sources = successful & repeated
        duplicate_verified = bool(stable_sources) and all(
            {n["id"] for n in before if n["source_id"] == source} ==
            {n["id"] for n in after if n["source_id"] == source}
            and next(row for row in second.sources if row.source_id == source).inserted == 0
            for source in stable_sources)
        direct_ids = {s.id for s in config.sources if s.collector == "webplus" and s.id in selected}
        direct_rows = [n for n in after if n["source_id"] in direct_ids]
        content_verified = any(n["content"] and n["metadata"].get("detail_status") == "success" for n in direct_rows)
        evidence = {
            "verified_at": iso_utc(utcnow()), "mode": "live_http_no_fixtures",
            "database": str(args.database), "first_fetch": first.to_dict(),
            "repeat_fetch": second.to_dict(), "notice_count_before_repeat": len(before),
            "notice_count_after_repeat": len(after),
            "query_verified": query_verified,
            "direct_content_verified": content_verified if direct_ids else None,
            "repeat_identity_verified": duplicate_verified if stable_sources else None,
            "sample_notices": [n.to_dict() for n in queried],
            "source_runs": service.recent_runs(),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k not in {"sample_notices", "source_runs"}}, ensure_ascii=False, indent=2))
    return 0 if successful and query_verified and duplicate_verified and (not direct_ids or content_verified) else 1


if __name__ == "__main__":
    sys.exit(main())
