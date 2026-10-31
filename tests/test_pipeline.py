"""Offline integration: real parsers, adapters, service and SQLite with fixture HTTP responses."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import tempfile
from unittest.mock import Mock
import unittest

from seu_pulse.collectors import HttpClient, RSSHubCollector, WebPlusCollector
from seu_pulse.config import Config
from seu_pulse.service import PulseService
from .test_collectors import FIXTURES, FakeResponse
from .test_models_storage import NOW, SOURCE


class PipelineTests(unittest.TestCase):
    def test_rss_collect_parse_persist_repeat_update_and_query(self):
        original = (FIXTURES / "notices.xml").read_bytes()
        opener = Mock()
        opener.open.side_effect = [FakeResponse(b"User-agent: *\nAllow: /"),
                                   FakeResponse(original), FakeResponse(original),
                                   FakeResponse(original.replace("测试 正文".encode(), "修订 正文".encode()).replace("测试 <b>正文".encode(), "修订 <b>正文".encode()))]
        client = HttpClient(opener=opener, sleeper=lambda _: None)
        with tempfile.TemporaryDirectory() as temp:
            config = Config(Path(temp) / "pipeline.db", "http://localhost:1200", (SOURCE,))
            with PulseService(config, collectors={"rsshub": RSSHubCollector(client, config.rsshub_base_url)}, clock=lambda: NOW) as service:
                first = service.fetch_notices()
                self.assertEqual(first.sources[0].inserted, 3)
                initial = {n.id: n for n in service.list_notices()}
                service.clock = lambda: NOW + timedelta(seconds=10)
                repeated = service.fetch_notices()
                self.assertEqual(repeated.sources[0].unchanged, 3)
                self.assertEqual(repeated.sources[0].inserted, 0)
                changed = service.fetch_notices()
                self.assertEqual(changed.sources[0].updated, 1)
                self.assertEqual(changed.sources[0].unchanged, 2)
                self.assertEqual(len(service.export_notices()["notices"]), 3)
                for notice in service.list_notices():
                    self.assertEqual(notice.first_seen_at, initial[notice.id].first_seen_at)
                    self.assertEqual(service.get_notice(notice.id), notice)

    def test_html_and_empty_feed_success_survive_invalid_source(self):
        html = replace(SOURCE, id="html", collector="html", route=None)
        empty = replace(SOURCE, id="empty", route="/empty")
        bad = replace(SOURCE, id="bad", route="/bad")
        opener = Mock()

        def serve(request, timeout):
            url = request.full_url
            if url.endswith("robots.txt"):
                return FakeResponse(b"User-agent: *\nAllow: /")
            if url.endswith("list.htm"):
                return FakeResponse((FIXTURES / "webplus.html").read_bytes())
            if url.endswith("/empty"):
                return FakeResponse(b"<rss><channel/></rss>")
            return FakeResponse(b"<html>upstream error</html>")

        opener.open.side_effect = serve
        client = HttpClient(opener=opener, sleeper=lambda _: None)
        with tempfile.TemporaryDirectory() as temp:
            config = Config(Path(temp) / "pipeline.db", "http://localhost:1200", (bad, html, empty))
            adapters = {"rsshub": RSSHubCollector(client, config.rsshub_base_url), "html": WebPlusCollector(client)}
            with PulseService(config, collectors=adapters, clock=lambda: NOW) as service:
                result = service.fetch_notices()
                self.assertEqual([r.status for r in result.sources], ["failed", "success", "success"])
                self.assertEqual(result.sources[1].inserted, 2)
                self.assertEqual(result.sources[2].read, 0)
                self.assertEqual(len(service.list_notices(source_id="html")), 2)
