from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须带时区")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def parse_published(raw: str | None) -> str | None:
    """Never assign a timezone to an ambiguous source date."""
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            value = parsedate_to_datetime(raw)
        except (ValueError, TypeError, OverflowError):
            return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return iso_utc(value)


def normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(unicodedata.normalize("NFKC", value).split()) or None


def canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username or parts.password:
            return None
        host = parts.hostname.lower().encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        if port and (parts.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
            host += f":{port}"
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", urlencode(sorted(query)), ""))
    except (ValueError, UnicodeError):
        return None


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass
class CollectedNotice:
    title: str
    url: str | None = None
    published_at: str | None = None
    summary: str | None = None
    content: str | None = None
    category: str | None = None
    metadata: dict = field(default_factory=dict)
    external_id: str | None = None


@dataclass
class Notice:
    id: str
    source_id: str
    title: str
    url: str | None
    published_at: str | None
    first_seen_at: str
    fetched_at: str
    summary: str | None
    content: str | None
    category: str
    content_hash: str
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NoticeContent:
    id: str
    url: str | None
    content: str | None
    metadata: dict


def convert_notice(item: CollectedNotice, source_id: str, category: str,
                   fetched_at: datetime) -> tuple[str, Notice]:
    title = normalized_text(item.title)
    if title is None:
        raise ValueError("通知标题不能为空")
    url = canonical_url(item.url)
    # URL first; otherwise feed GUID, then normalized title. Never include mutable body or fetch time.
    identity = "url:" + url if url else (
        "external:" + item.external_id if item.external_id else "title:" + title)
    if not isinstance(item.metadata, dict):
        raise ValueError("metadata 必须为 JSON object")
    metadata = {k: v for k, v in item.metadata.items() if v is not None}
    # Validate at the adapter boundary so malformed source metadata fails only that source.
    json.dumps(metadata, ensure_ascii=False, sort_keys=True, allow_nan=False)
    metadata["identity_basis"] = "url" if url else ("external_id" if item.external_id else "title")
    if item.external_id:
        metadata["external_id"] = item.external_id
    published = parse_published(item.published_at)
    if item.published_at and published is None:
        metadata.setdefault("raw_published_at", item.published_at)
    timestamp = iso_utc(fetched_at)
    notice = Notice(digest([source_id, identity]), source_id, title, url, published, timestamp,
                    timestamp, normalized_text(item.summary), normalized_text(item.content),
                    normalized_text(item.category) or category, "", metadata)
    notice.content_hash = notice_hash(notice)
    return identity, notice


def notice_hash(notice: Notice) -> str:
    # Metadata is provenance, excluded from the effective-content fingerprint.
    return digest([notice.title, notice.url, notice.published_at, notice.summary,
                   notice.content, notice.category])


@dataclass
class SourceResult:
    source_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    read: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    error_category: str | None = None
    error_summary: str | None = None


@dataclass
class FetchResult:
    run_id: str
    started_at: str
    finished_at: str | None = None
    sources: list[SourceResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["totals"] = {key: sum(getattr(s, key) for s in self.sources)
                            for key in ("read", "inserted", "updated", "unchanged")}
        result["totals"].update({name: sum(s.status == state for s in self.sources)
                                 for name, state in (("successful_sources", "success"),
                                                     ("failed_sources", "failed"),
                                                     ("skipped_sources", "skipped"))})
        return result
