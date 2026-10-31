"""Capture one original list HTML and two article samples per direct source on the server."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from seu_pulse.collectors import HttpClient, SourceError
from seu_pulse.config import load_config
from seu_pulse.models import iso_utc, utcnow
from seu_pulse.webpages import parse_article, parse_direct_list


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--source", action="append", dest="source_ids")
    parser.add_argument("--output-dir", type=Path, default=Path("data/source-inspection"))
    parser.add_argument("--max-article-attempts", type=int, default=6,
                        help="为找到两篇可读正文最多检查的本站文章数，默认 6")
    args = parser.parse_args()
    if not 2 <= args.max_article_attempts <= 20:
        parser.error("max-article-attempts 必须在 2..20")
    config = load_config(args.config)
    direct = {s.id: s for s in config.sources if s.collector == "webplus"}
    selected = args.source_ids if args.source_ids is not None else list(direct)
    if not selected or set(selected) - direct.keys():
        parser.error("必须选择已配置的 webplus 来源")
    client, results = HttpClient(), []
    for source_id in dict.fromkeys(selected):
        source = direct[source_id]
        folder = args.output_dir / source_id
        folder.mkdir(parents=True, exist_ok=True)
        row = {"source_id": source_id, "url": source.url, "list_verified": False, "articles": []}
        try:
            data = client.get(source.url, source)
            (folder / "list.html").write_bytes(data)
            listed = parse_direct_list(data, source)
            row["list_verified"] = bool(listed)
            row["listed_notices"] = len(listed)
            # Sample actual local article pages, rather than external redirect pointers.
            items = [item for item in listed if urlsplit(item.url).path != "/_redirect"][:args.max_article_attempts]
            for index, item in enumerate(items, 1):
                article = {"url": item.url, "title": item.title, "metadata": item.metadata, "content_verified": False}
                try:
                    raw = client.get(item.url, source)
                    (folder / f"article-{index}.html").write_bytes(raw)
                    parsed = parse_article(raw, item, source)
                    article.update(title=parsed.title, metadata=parsed.metadata,
                                   content_length=len(parsed.content), content_verified=True)
                except SourceError as exc:
                    article.update(error_category=exc.category, error_summary=exc.summary)
                row["articles"].append(article)
                if sum(a["content_verified"] for a in row["articles"]) >= 2:
                    break
        except SourceError as exc:
            row.update(error_category=exc.category, error_summary=exc.summary)
        results.append(row)
    evidence = {"verified_at": iso_utc(utcnow()), "mode": "original_http_html", "sources": results}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if all(r["list_verified"] and sum(a["content_verified"] for a in r["articles"]) >= 2
                   for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
