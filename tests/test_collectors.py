from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request

from seu_pulse.collectors import HttpClient, PublicRedirects, SourceError, parse_feed, parse_webplus
from .test_models_storage import SOURCE


FIXTURES = Path(__file__).parent / "fixtures"


class CollectorTests(unittest.TestCase):
    def test_rss_mapping_and_dates(self):
        items = parse_feed((FIXTURES / "notices.xml").read_bytes(), SOURCE)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].content, "测试 正文")
        self.assertEqual(items[0].published_at, "2026-10-19T01:30:00.000000+00:00")
        self.assertEqual(items[0].url, "https://example.edu.cn/2026/1019/c1a1/page.htm")
        self.assertEqual(items[1].url, "https://example.edu.cn/2026/1018/c1a2/page.htm")
        self.assertIsNone(items[1].published_at)
        self.assertEqual(items[1].metadata["raw_published_at"], "2026-10-18")
        self.assertIsNone(items[2].url)
        self.assertEqual(items[2].external_id, "stable-guid")

    def test_atom_mapping(self):
        item = parse_feed((FIXTURES / "atom.xml").read_bytes(), SOURCE)[0]
        self.assertEqual(item.url, "https://example.edu.cn/2026/1019/c1a3/page.htm")
        self.assertEqual(item.content, "正文第一段 正文第二段")
        self.assertEqual(item.summary, "摘要")

    def test_feed_empty_distinct_from_parse_failure(self):
        self.assertEqual(parse_feed(b"<rss><channel/></rss>", SOURCE), [])
        for invalid in (b"<html>Login</html>", b"not xml", b"<rss/>", b"<rss><channel><item/></channel></rss>", b'<!DOCTYPE rss [<!ENTITY a "x">]><rss/>'):
            with self.subTest(invalid=invalid), self.assertRaises(SourceError):
                parse_feed(invalid, SOURCE)

    def test_static_webplus_only_public_articles_no_timezone_inference(self):
        items = parse_webplus((FIXTURES / "webplus.html").read_bytes(), SOURCE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "完整测试标题")
        self.assertEqual(items[0].metadata["raw_published_at"], "2026-10-19")
        self.assertIsNone(items[0].published_at)
        self.assertIsNone(items[0].content)
        with self.assertRaises(SourceError):
            parse_webplus(b"<html><form>login</form></html>", SOURCE)


class FakeResponse(BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain; charset=utf-8"


class HttpTests(unittest.TestCase):
    def test_robots_cached_timeout_and_spacing(self):
        opener = Mock()
        opener.open.side_effect = [FakeResponse(b"User-agent: *\nDisallow: /private"), FakeResponse(b"one"), FakeResponse(b"two")]
        sleep = Mock()
        client = HttpClient(opener=opener, sleeper=sleep, monotonic=lambda: 1)
        self.assertEqual(client.get(SOURCE.url, SOURCE), b"one")
        self.assertEqual(client.get(SOURCE.url, SOURCE), b"two")
        self.assertEqual(opener.open.call_count, 3)
        self.assertTrue(all(c.kwargs["timeout"] == 15 for c in opener.open.call_args_list))
        sleep.assert_called_with(1)
        with self.assertRaises(SourceError) as context:
            client.get("https://example.edu.cn/private", SOURCE)
        self.assertEqual(context.exception.category, "robots_denied")
        self.assertEqual(opener.open.call_count, 3)

    def test_network_retries_are_bounded_and_sanitized(self):
        opener = Mock()
        opener.open.side_effect = URLError("https://secret:password@example.test/?token=secret")
        client = HttpClient(opener=opener, sleeper=Mock())
        with self.assertRaises(SourceError) as context:
            client.get(SOURCE.url, SOURCE)
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(context.exception.category, "network")
        self.assertNotIn("secret", str(context.exception))

    def test_transient_http_retried_403_not_retried(self):
        opener = Mock()
        opener.open.side_effect = [HTTPError(SOURCE.url, 503, "unavailable", {}, None), FakeResponse(b"ok")]
        client = HttpClient(opener=opener, sleeper=Mock())
        self.assertEqual(client._request(SOURCE.url, SOURCE)[0], b"ok")
        opener.open.reset_mock(side_effect=True)
        opener.open.side_effect = HTTPError(SOURCE.url, 403, "forbidden", {}, None)
        with self.assertRaises(SourceError) as context:
            client.get(SOURCE.url, SOURCE)
        self.assertEqual(context.exception.category, "access_control")
        self.assertEqual(opener.open.call_count, 1)

    def test_missing_robots_permitted_and_oversize_rejected(self):
        opener = Mock()
        opener.open.side_effect = [HTTPError(SOURCE.url, 404, "missing", {}, None), FakeResponse(b"ok")]
        client = HttpClient(opener=opener, sleeper=Mock())
        self.assertEqual(client.get(SOURCE.url, SOURCE), b"ok")
        client.MAX_BYTES = 1
        opener.open.side_effect = [FakeResponse(b"too big")]
        with self.assertRaises(SourceError) as context:
            client.get(SOURCE.url, SOURCE)
        self.assertEqual(context.exception.category, "response_too_large")

    def test_login_cross_host_downgrade_redirects_blocked(self):
        redirects = PublicRedirects()
        for target in ("https://newids.seu.edu.cn/login", "http://example.edu.cn/a", "https://example.edu.cn/login"):
            with self.assertRaises(SourceError):
                redirects.redirect_request(Request(SOURCE.url), None, 302, "", {}, target)
