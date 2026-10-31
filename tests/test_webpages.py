from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import Mock
import unittest

from seu_pulse.collectors import HttpClient, RSSHubCollector, SourceError
from seu_pulse.config import Config, ConfigError, load_config
from seu_pulse.service import PulseService
from seu_pulse.webpages import DirectWebPlusCollector, parse_article, parse_direct_list
from .test_collectors import FIXTURES, FakeResponse
from .test_models_storage import NOW, SOURCE


DIRECT = replace(SOURCE, id="direct", collector="webplus", route=None)
LIST = (FIXTURES / "direct-list.html").read_bytes()
ARTICLE = (FIXTURES / "direct-article.html").read_bytes()


class DirectTests(unittest.TestCase):
    def test_list_titles_dates_redirects_and_limits(self):
        items = parse_direct_list(LIST, DIRECT)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[1].title, "测试卡片通知")
        self.assertEqual(items[1].metadata["raw_published_at"], "2026 10.14")
        self.assertIsNone(items[0].published_at)
        self.assertTrue(items[2].url.startswith("https://example.edu.cn/_redirect?"))
        self.assertEqual(len(parse_direct_list(LIST, replace(DIRECT, max_items=2))), 2)
        with self.assertRaises(SourceError):
            parse_direct_list(b"<html>nothing</html>", DIRECT)

    def test_configured_list_scope_excludes_masthead_articles(self):
        data = b'<a href="/2026/1001/c2a5/page.htm">Unrelated banner</a>' + b'<div id="wp_news_w8">' + LIST + b'</div>'
        source = replace(DIRECT, list_container_id="wp_news_w8")
        items = parse_direct_list(data, source)
        self.assertEqual(len(items), 3)
        self.assertNotIn("Unrelated banner", [i.title for i in items])
        with self.assertRaises(SourceError):
            parse_direct_list(LIST, source)
        by_class = replace(DIRECT, list_container_class="column-list")
        self.assertEqual(len(parse_direct_list(b'<div class="column-list">' + LIST + b'</div>', by_class)), 3)

    def test_article_extracts_only_body_and_explicit_publication_metadata(self):
        item = parse_direct_list(LIST, DIRECT)[0]
        parsed = parse_article(ARTICLE, item, DIRECT)
        self.assertEqual(parsed.title, "测试完整通知标题")
        self.assertEqual(parsed.content, "测试正文第一段 测试正文第二段")
        self.assertIsNone(parsed.published_at)
        raw = ARTICLE.replace(b'content="2026-10-15"', b'content="2026-10-15T10:00:00+08:00"')
        self.assertEqual(parse_article(raw, item, DIRECT).published_at, "2026-10-15T02:00:00.000000+00:00")
        alternate = ARTICLE.replace(b'wp_articlecontent', b'Article_Content')
        self.assertEqual(parse_article(alternate, item, DIRECT).content, parsed.content)

    def test_campus_ip_restrictions_empty_body_and_unmatched_container(self):
        item = parse_direct_list(LIST, DIRECT)[0]
        for text, category in (("<html>提示：您当前ip并非校内地址，该信息仅允许校内地址访问</html>", "access_control"),
                               ('<div class="wp_articlecontent"><img src="a.png"></div>', "parse"),
                               ("<html>login</html>", "parse")):
            with self.assertRaises(SourceError) as context:
                parse_article(text.encode(), item, DIRECT)
            self.assertEqual(context.exception.category, category)

    def test_detail_failure_preserves_list_and_existing_body(self):
        client = Mock()
        client.get.side_effect = [LIST, ARTICLE, SourceError("access_control", "restricted"), SourceError("access_control", "redirect")]
        collector = DirectWebPlusCollector(client)
        with tempfile.TemporaryDirectory() as temp:
            config = Config(Path(temp) / "direct.db", sources=(DIRECT,))
            with PulseService(config, collectors={"webplus": collector}, clock=lambda: NOW) as service:
                result = service.fetch_notices()
                self.assertEqual(result.sources[0].inserted, 3)
                notices = service.list_notices()
                self.assertEqual(sum(n.content is not None for n in notices), 1)
                self.assertEqual(sum(n.metadata["detail_status"] == "failed" for n in notices), 2)
                client.get.side_effect = [LIST, SourceError("network", "offline"), SourceError("network", "offline"), SourceError("network", "offline")]
                service.fetch_notices()
                # The body survives a later failure even though the latest detail status records it.
                self.assertEqual(sum(n.content is not None for n in service.list_notices()), 1)
                client.get.side_effect = [LIST, ARTICLE.replace("测试正文第一段".encode(), "修订正文第一段".encode()),
                                          SourceError("network", "offline"), SourceError("network", "offline")]
                changed = service.fetch_notices()
                self.assertEqual(changed.sources[0].updated, 1)
                recovered = next(n for n in service.list_notices() if n.content is not None)
                self.assertEqual(recovered.metadata["detail_error"], {})
                self.assertIn("修订正文第一段", recovered.content)

    def test_direct_and_rsshub_share_one_service_and_preserve_failure_isolation(self):
        opener = Mock()

        def serve(request, timeout):
            url = request.full_url
            if url.endswith("robots.txt"):
                return FakeResponse(b"User-agent: *\nAllow: /")
            if url.endswith("/list.htm"):
                return FakeResponse(LIST)
            if "/seu/" in url:
                return FakeResponse((FIXTURES / "notices.xml").read_bytes())
            return FakeResponse(ARTICLE)

        opener.open.side_effect = serve
        client = HttpClient(opener=opener, sleeper=lambda _: None)
        bad_adapter = Mock()
        bad_adapter.collect.side_effect = SourceError("network", "failed")
        with tempfile.TemporaryDirectory() as temp:
            config = Config(Path(temp) / "mixed.db", "http://localhost:1200", (DIRECT, SOURCE))
            adapters = {"webplus": DirectWebPlusCollector(client), "rsshub": RSSHubCollector(client, config.rsshub_base_url)}
            with PulseService(config, collectors=adapters, clock=lambda: NOW) as service:
                first = service.fetch_notices()
                self.assertEqual(first.to_dict()["totals"]["successful_sources"], 2)
                self.assertEqual(len(service.list_notices()), 6)
                repeated = service.fetch_notices()
                self.assertEqual(repeated.to_dict()["totals"]["inserted"], 0)
                self.assertEqual(repeated.to_dict()["totals"]["unchanged"], 6)
                service.collectors["webplus"] = bad_adapter
                isolated = service.fetch_notices()
                self.assertEqual([r.status for r in isolated.sources], ["failed", "success"])
                self.assertEqual(len(service.list_notices()), 6)

    def test_direct_only_config_requires_no_rsshub_address_and_old_config_still_loads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text('[[sources]]\nid="direct"\nname="Direct"\ncollector="webplus"\nurl="https://example.edu.cn/list.htm"\n')
            self.assertIsNone(load_config(path).rsshub_base_url)
            path.write_text(path.read_text().replace('collector="webplus"', 'collector="rsshub"') + 'route="/seu/cse/tzgg"\n')
            self.assertEqual(load_config(path).rsshub_base_url, "https://rsshub.app")
        for changes in ({"max_items": 0}, {"max_items": True}, {"content_classes": []}, {"content_classes": ["div.foo"]}):
            with self.assertRaises(ConfigError):
                replace(DIRECT, **changes)
