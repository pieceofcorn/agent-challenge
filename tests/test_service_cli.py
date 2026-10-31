from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import Mock, patch
import unittest

from seu_pulse.cli import main
from seu_pulse.collectors import SourceError
from seu_pulse.config import Config, ConfigError, SourceConfig, load_config
from seu_pulse.models import CollectedNotice
from seu_pulse.service import PulseService
from .test_models_storage import NOW, SOURCE


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.config = Config(self.path, "http://localhost:1200", (SOURCE, replace(SOURCE, id="bad"), replace(SOURCE, id="off", enabled=False)))
        self.collector = Mock()
        self.service = PulseService(self.config, collectors={"rsshub": self.collector}, clock=lambda: NOW)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_failure_isolation_incremental_counts_runs_and_json(self):
        self.collector.collect.side_effect = [[CollectedNotice("A", "https://example.edu.cn/a", content="old")], SourceError("network", "连接失败")]
        first = self.service.fetch_notices()
        self.assertEqual(first.to_dict()["totals"], {"read": 1, "inserted": 1, "updated": 0, "unchanged": 0, "successful_sources": 1, "failed_sources": 1, "skipped_sources": 0})
        notice = self.service.list_notices()[0]
        self.assertEqual(self.service.get_notice_content(notice.id).content, "old")
        self.collector.collect.side_effect = [[CollectedNotice("A", "https://example.edu.cn/a")]]
        second = self.service.fetch_notices(source_ids=["test"])
        self.assertEqual(second.sources[0].unchanged, 1)
        self.collector.collect.side_effect = [[CollectedNotice("A", "https://example.edu.cn/a", content="new")]]
        third = self.service.fetch_notices(source_ids=["test"])
        self.assertEqual(third.sources[0].updated, 1)
        self.assertEqual(self.service.get_notice(notice.id).content, "new")
        exported = json.loads(json.dumps(self.service.export_notices()))
        self.assertEqual(exported["schema_version"], "1")
        self.assertEqual(len(exported["notices"]), 1)
        runs = self.service.recent_runs()
        self.assertEqual(len(runs), 4)
        self.assertIn("network", [r["error_category"] for r in runs])
        self.assertIsNone(self.service.get_notice("absent"))
        self.assertIsNone(self.service.get_notice_content("absent"))

    def test_empty_success_and_null_content_distinct_from_missing(self):
        self.collector.collect.return_value = []
        result = self.service.fetch_notices(source_ids=["test"])
        self.assertEqual(result.sources[0].status, "success")
        self.assertEqual(result.sources[0].read, 0)
        self.collector.collect.return_value = [CollectedNotice("No body")]
        self.service.fetch_notices(source_ids=["test"])
        result = self.service.get_notice_content(self.service.list_notices()[0].id)
        self.assertIsNotNone(result)
        self.assertIsNone(result.content)

    def test_parameter_errors_create_no_run(self):
        for ids in (["missing"], "test", [1]):
            with self.assertRaises(ValueError):
                self.service.fetch_notices(source_ids=ids)
        with self.assertRaises(ValueError):
            self.service.list_notices(source_id="missing")
        self.assertEqual(self.service.recent_runs(), [])
        self.assertFalse(self.collector.collect.called)

    def test_source_conversion_failure_is_atomic(self):
        self.collector.collect.side_effect = [[CollectedNotice("A"), CollectedNotice(" ")], [CollectedNotice("B")]]
        result = self.service.fetch_notices()
        self.assertEqual([s.status for s in result.sources], ["failed", "success"])
        self.assertEqual([n.title for n in self.service.list_notices()], ["B"])

    def test_storage_error_is_not_hidden(self):
        self.collector.collect.return_value = [CollectedNotice("A")]
        with patch.object(self.service.storage, "upsert", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.fetch_notices(source_ids=["test"])
        self.assertEqual(self.service.list_notices(), [])

    def test_persistent_interval_also_applies_to_failure_and_explicit_selection(self):
        self.service.close()
        config = replace(self.config, sources=(replace(SOURCE, interval_seconds=60),))
        self.service = PulseService(config, collectors={"rsshub": self.collector}, clock=lambda: NOW)
        self.collector.collect.side_effect = SourceError("network", "失败")
        self.assertEqual(self.service.fetch_notices().sources[0].status, "failed")
        self.service.close()
        self.service = PulseService(config, collectors={"rsshub": self.collector}, clock=lambda: NOW + timedelta(seconds=59))
        self.assertEqual(self.service.fetch_notices(source_ids=["test"]).sources[0].status, "skipped")
        self.assertEqual(self.collector.collect.call_count, 1)
        self.service.clock = lambda: NOW + timedelta(seconds=60)
        self.collector.collect.side_effect = None
        self.collector.collect.return_value = []
        self.assertEqual(self.service.fetch_notices().sources[0].status, "success")


class ConfigCliTests(unittest.TestCase):
    def test_config_repository_and_strict_validation(self):
        config = load_config("config.toml")
        self.assertEqual(len(config.sources), 6)
        self.assertEqual([s.id for s in config.sources if s.enabled], ["jwc-international", "wjx-notices"])
        self.assertTrue(config.database.is_absolute())
        for changes in ({"timeout": 0}, {"retries": 10}, {"id": "../a"}, {"collector": "unknown"}, {"enabled": "true"}, {"route": "//example.test/a"}, {"url": "https://user:secret@example.test/"}, {"interval_seconds": float("nan")}):
            with self.subTest(changes=changes), self.assertRaises(ConfigError):
                replace(SOURCE, **changes)
        with self.assertRaises(ConfigError):
            Config(Path("test.db"), "https://rsshub.app", (SOURCE, SOURCE))

    def test_cli_queries_export_exit_codes_and_error_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "config.toml"
            config_path.write_text('[app]\ndatabase="test.db"\n[[sources]]\nid="test"\nname="Test"\ncollector="rsshub"\nurl="https://example.edu.cn/list.htm"\nroute="/seu/cse/tzgg"\ninterval_seconds=0\n')
            config = load_config(config_path)
            adapter = Mock()
            adapter.collect.return_value = [CollectedNotice("CLI test", url="https://example.edu.cn/a")]
            with PulseService(config, collectors={"rsshub": adapter}, clock=lambda: NOW) as service:
                service.fetch_notices()
                notice_id = service.list_notices()[0].id
            for args, expected_code in ((["list"], 0), (["get", notice_id], 0), (["get", "absent"], 3), (["runs"], 0), (["export"], 0)):
                output = StringIO()
                with redirect_stdout(output):
                    code = main(["--config", str(config_path), *args])
                self.assertEqual(code, expected_code)
                json.loads(output.getvalue())
            output_path = root / "export.json"
            self.assertEqual(main(["--config", str(config_path), "export", "--output", str(output_path)]), 0)
            self.assertEqual(json.loads(output_path.read_text())["schema_version"], "1")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["--config", str(config_path), "fetch", "--source", "missing"]), 2)
                self.assertEqual(main(["--config", str(config_path), "list", "--limit", "0"]), 2)
                with self.assertRaises(SystemExit) as context:
                    main(["--config", str(config_path), "list", "--since", "2026-10-20"])
                self.assertEqual(context.exception.code, 2)

    def test_cli_fetch_failure_status_and_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(Path(temp) / "test.db", "http://localhost:1200", (SOURCE,))
            adapter = Mock()
            adapter.collect.side_effect = SourceError("network", "测试网络失败")
            service = PulseService(config, collectors={"rsshub": adapter}, clock=lambda: NOW)
            out = StringIO()
            with patch("seu_pulse.cli.PulseService.from_config", return_value=service), redirect_stdout(out):
                self.assertEqual(main(["fetch"]), 1)
            result = json.loads(out.getvalue())
            self.assertEqual(result["totals"]["failed_sources"], 1)
            self.assertEqual(result["sources"][0]["error_category"], "network")
