"""Direct WebPlus list and article collection, using the existing HTTP/HTML implementation."""
from __future__ import annotations

from dataclasses import replace
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from .collectors import HtmlTree, HttpClient, Node, SourceError
from .config import SourceConfig
from .models import CollectedNotice, canonical_url, normalized_text, parse_published


ARTICLE_PATH = re.compile(r"/\d{4}/\d{4}/c\d+a\d+/page\.(?:htm|psp)$")
DATE = re.compile(r"\b(\d{4})\s*[-./年 ]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})(?:日)?\b")


def html_tree(data: bytes) -> HtmlTree:
    match = re.search(br"charset\s*=\s*['\"]?([\w-]+)", data[:4096], re.I)
    encoding = match.group(1).decode("ascii") if match else "utf-8-sig"
    try:
        return HtmlTree(data.decode(encoding))
    except (UnicodeError, LookupError) as exc:
        raise SourceError("parse", "网页字符编码解析失败") from exc


def has_class(node: Node, classes) -> bool:
    return bool(set(node.attrs.get("class", "").split()) & set(classes))


def public_article_url(href: str, source: SourceConfig) -> str | None:
    url = canonical_url(urljoin(source.url, href))
    if not url or urlsplit(url).netloc != urlsplit(source.url).netloc:
        return None
    parts = urlsplit(url)
    if ARTICLE_PATH.search(parts.path):
        return url
    # WebPlus's stable article pointer can legitimately redirect to an external link.
    # Keep its list notice; the HTTP client's redirect policy prevents following external sites.
    if parts.path == "/_redirect" and parse_qs(parts.query).get("articleId", [""])[0].isdigit():
        return url
    return None


def parse_direct_list(data: bytes, source: SourceConfig) -> list[CollectedNotice]:
    tree = html_tree(data)
    scope = tree.root
    if source.list_container_id or source.list_container_class:
        scope = next((n for n in tree.root.walk()
                      if (source.list_container_id is None or n.attrs.get("id") == source.list_container_id)
                      and (source.list_container_class is None or has_class(n, {source.list_container_class}))), None)
        if scope is None:
            raise SourceError("parse", "配置的栏目列表容器未匹配；不退回整页搜索以免混入其他栏目")
    items = {}
    for node in scope.walk():
        if node.tag != "a":
            continue
        url = public_article_url(node.attrs.get("href", ""), source)
        if not url or url in items:
            continue
        title = normalized_text(node.attrs.get("title"))
        if not title:
            heading = next((n for n in node.walk() if n.tag in {"h1", "h2", "h3", "h4", "h5"}
                            or has_class(n, {"news_title", "Article_Title"})), None)
            title = normalized_text(heading.text() if heading else node.text())
        if not title:
            continue
        # A date can be inside the anchor (WJX cards), or beside it in a li/tr (JWC lists).
        row = node
        while row.parent and row.tag not in {"li", "tr"}:
            row = row.parent
        match = DATE.search((row if row.tag in {"li", "tr"} else node).text())
        metadata = {"raw_published_at": match.group(0)} if match else {}
        items[url] = CollectedNotice(title=title, url=url, category=source.category, metadata=metadata)
        if len(items) >= source.max_items:
            break
    if not items and not source.allow_empty:
        raise SourceError("parse", "列表中未找到本站 WebPlus 通知；需核对原始 HTML 或访问限制")
    return list(items.values())


def parse_article(data: bytes, item: CollectedNotice, source: SourceConfig) -> CollectedNotice:
    tree = html_tree(data)
    # Some campus-IP restrictions return HTTP 200 with a short access notice.
    page_text = tree.root.text().lower()
    if any(text in page_text for text in ("您当前ip并非校内地址", "仅允许校内地址访问", "请输入验证码")):
        raise SourceError("access_control", "正文返回校内地址或验证码访问限制，未尝试绕过")
    body = next((n for n in tree.root.walk() if has_class(n, source.content_classes)), None)
    if body is None:
        raise SourceError("parse", "正文容器未匹配；需核对原始 HTML 中的 content_classes")
    content = normalized_text(body.text())
    if content is None:
        raise SourceError("parse", "正文容器无可提取文本，可能仅含图片或附件")
    title = next((n.attrs.get("content") for n in tree.root.walk()
                  if n.tag == "meta" and n.attrs.get("name", "").lower() == "articletitle"), None)
    if not title:
        heading = next((n for n in tree.root.walk()
                        if has_class(n, {"arti_title", "Article_Title"}) and not has_class(n, source.content_classes)), None)
        title = heading.text() if heading else None
    metadata = {**item.metadata, "detail_status": "success", "detail_error": {}}
    # Only metadata that explicitly identifies publication time can replace the list date.
    raw_date = next((n.attrs.get("content") for n in tree.root.walk()
                     if n.tag == "meta" and n.attrs.get("name", "").lower() == "publishtime"), None)
    published = item.published_at
    if raw_date:
        metadata["raw_published_at"] = raw_date
        published = parse_published(raw_date)
    return replace(item, title=normalized_text(title) or item.title, content=content,
                   published_at=published, metadata=metadata)


class DirectWebPlusCollector:
    def __init__(self, client: HttpClient):
        self.client = client

    def collect(self, source: SourceConfig) -> list[CollectedNotice]:
        items = parse_direct_list(self.client.get(source.url, source), source)
        result = []
        for item in items:
            try:
                result.append(parse_article(self.client.get(item.url, source), item, source))
            except SourceError as exc:
                # A failed detail must not discard a valid list entry, or erase an existing body.
                result.append(replace(item, metadata={**item.metadata, "detail_status": "failed",
                                                       "detail_error": {"category": exc.category, "summary": exc.summary}}))
        return result
