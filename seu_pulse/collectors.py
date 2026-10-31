from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

from .config import SourceConfig
from .models import CollectedNotice, canonical_url, normalized_text, parse_published


class SourceError(Exception):
    def __init__(self, category: str, summary: str):
        super().__init__(summary)
        self.category = category
        self.summary = summary


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (old.hostname != new.hostname or new.scheme not in {"http", "https"}
                or new.username or new.password or (old.scheme == "https" and new.scheme != "https")
                or re.search(r"(?:login|captcha|newids|sso)", new.path, re.I)):
            raise SourceError("access_control", "拒绝跨站或登录重定向；未尝试绕过访问控制")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpClient:
    USER_AGENT = "SEU-Pulse/0.1 (public campus notices)"
    MAX_BYTES = 5 * 1024 * 1024

    def __init__(self, *, opener=None, sleeper=time.sleep, monotonic=time.monotonic):
        self.opener = opener or build_opener(PublicRedirects())
        self.sleep = sleeper
        self.monotonic = monotonic
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}

    def _request(self, url: str, source: SourceConfig) -> tuple[bytes, str | None]:
        host = urlsplit(url).netloc
        for attempt in range(source.retries + 1):
            last = self._last_request.get(host)
            if last is not None:
                self.sleep(max(0, source.request_interval_seconds - (self.monotonic() - last)))
            self._last_request[host] = self.monotonic()
            try:
                request = Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/html;q=0.9, */*;q=0.1"})
                with self.opener.open(request, timeout=source.timeout) as response:
                    data = response.read(self.MAX_BYTES + 1)
                    if len(data) > self.MAX_BYTES:
                        raise SourceError("response_too_large", "响应超过 5 MiB 限制")
                    return data, response.headers.get_content_charset()
            except HTTPError as exc:
                code = exc.code
                exc.close()
                if code in {401, 403}:
                    raise SourceError("access_control", f"HTTP {code}；未尝试绕过访问控制") from exc
                if code not in {408, 429, 500, 502, 503, 504} or attempt == source.retries:
                    raise SourceError("http", f"HTTP {code}") from exc
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                if attempt == source.retries:
                    # Do not include exception URLs, query credentials, or proxy configuration in logs.
                    raise SourceError("network", "网络连接、DNS、TLS 或请求超时失败") from exc
            if attempt < source.retries:
                self.sleep(min(2 ** attempt, 4))
        raise AssertionError("unreachable")

    def get(self, url: str, source: SourceConfig) -> bytes:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            robots = RobotFileParser()
            try:
                data, _ = self._request(origin + "/robots.txt", source)
                robots.parse(data.decode("utf-8", errors="replace").splitlines())
            except SourceError as exc:
                if exc.category == "http" and exc.summary in {"HTTP 404", "HTTP 410"}:
                    robots.parse([])
                else:
                    raise
            self._robots[origin] = robots
        robots = self._robots[origin]
        if not robots.can_fetch(self.USER_AGENT, url):
            raise SourceError("robots_denied", "robots.txt 不允许访问该栏目")
        delay = robots.crawl_delay(self.USER_AGENT) or 0
        if delay > source.request_interval_seconds:
            self.sleep(delay - source.request_interval_seconds)
        return self._request(url, source)[0]


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    parent: Node | None = None
    children: list = field(default_factory=list)

    def text(self) -> str:
        if self.tag in {"script", "style", "noscript"}:
            return ""
        return " ".join(child.text() if isinstance(child, Node) else child for child in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class HtmlTree(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node("root")
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def plain_html(value: str | None) -> str | None:
    return normalized_text(HtmlTree(value).root.text()) if value else None


def _field(node, names):
    for child in node:
        if child.tag.rsplit("}", 1)[-1] in names:
            # Atom XHTML needs its serialized markup to preserve word boundaries.
            return ET.tostring(child, encoding="unicode") if len(child) else child.text
    return None


def parse_feed(data: bytes, source: SourceConfig) -> list[CollectedNotice]:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", data, re.I):
        raise SourceError("parse", "不支持含 DTD 或实体声明的 XML")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise SourceError("parse", "RSS/Atom XML 解析失败") from exc
    kind = root.tag.rsplit("}", 1)[-1]
    if kind == "rss":
        channel = root.find("channel")
        if channel is None:
            raise SourceError("parse", "RSS 缺少 channel")
        entries = channel.findall("item")
    elif kind == "feed":
        entries = [x for x in root if x.tag.rsplit("}", 1)[-1] == "entry"]
    else:
        raise SourceError("parse", "响应不是 RSS/Atom，可能为错误页或登录页")
    items = []
    for entry in entries:
        title = plain_html(_field(entry, {"title"}))
        if not title:
            raise SourceError("parse", "订阅条目缺少标题")
        link = _field(entry, {"link"}) if kind == "rss" else None
        if kind == "feed":
            for node in entry:
                if node.tag.rsplit("}", 1)[-1] == "link" and node.get("rel", "alternate") == "alternate":
                    link = node.get("href")
                    break
        guid = _field(entry, {"guid", "id"})
        raw_date = _field(entry, {"pubDate", "published", "date"})
        description = plain_html(_field(entry, {"description", "summary"}))
        content = plain_html(_field(entry, {"encoded", "content"}))
        if kind == "rss" and content is None:
            content = description  # RSSHub official handlers use description for article text.
        metadata = {"raw_published_at": raw_date} if raw_date else {}
        items.append(CollectedNotice(title=title, url=canonical_url(urljoin(source.url, link)) if link else None,
                                     published_at=parse_published(raw_date), summary=description,
                                     content=content, category=source.category, metadata=metadata,
                                     external_id=guid))
    return items


def parse_webplus(data: bytes, source: SourceConfig) -> list[CollectedNotice]:
    encoding_match = re.search(br"charset\s*=\s*['\"]?([a-zA-Z0-9_-]+)", data[:4096], re.I)
    encoding = encoding_match.group(1).decode("ascii") if encoding_match else "utf-8"
    try:
        html = data.decode(encoding)
    except (UnicodeError, LookupError) as exc:
        raise SourceError("parse", "网页字符编码解析失败") from exc
    tree = HtmlTree(html)
    items = {}
    for node in tree.root.walk():
        if node.tag != "a":
            continue
        href = node.attrs.get("href", "")
        url = canonical_url(urljoin(source.url, href))
        # One stable WebPlus article URL format, no broad selector guessing.
        if not url or urlsplit(url).hostname != urlsplit(source.url).hostname:
            continue
        if not re.search(r"/\d{4}/\d{4}/c\d+a\d+/page\.(?:htm|psp)$", urlsplit(url).path):
            continue
        title = normalized_text(node.attrs.get("title") or node.text())
        if not title:
            continue
        container = node.parent
        while container and container.parent and container.tag not in {"li", "tr"}:
            container = container.parent
        raw_date = None
        if container and container.tag in {"li", "tr"}:
            match = re.search(r"\b\d{4}[-./]\d{2}[-./]\d{2}\b", container.text())
            raw_date = match.group(0) if match else None
        metadata = {"raw_published_at": raw_date} if raw_date else {}
        items[url] = CollectedNotice(title=title, url=url, category=source.category, metadata=metadata)
    if not items and not source.allow_empty:
        raise SourceError("parse", "未找到 WebPlus 公开文章；可能改版、登录页或确实为空，需人工核验")
    return list(items.values())


class RSSHubCollector:
    def __init__(self, client: HttpClient, base_url: str):
        self.client, self.base_url = client, base_url

    def collect(self, source: SourceConfig) -> list[CollectedNotice]:
        return parse_feed(self.client.get(self.base_url.rstrip("/") + source.route, source), source)


class WebPlusCollector:
    def __init__(self, client: HttpClient):
        self.client = client

    def collect(self, source: SourceConfig) -> list[CollectedNotice]:
        return parse_webplus(self.client.get(source.url, source), source)
