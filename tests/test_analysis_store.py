"""Persistence boundaries and append-only compatibility, with no model network calls."""
from copy import deepcopy
from dataclasses import replace
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from seu_pulse.analysis import AnalysisService, OUTPUT_EXAMPLE
from seu_pulse.analysis_store import AnalysisAttempt, AnalysisStore, NoticeAnalysis
from seu_pulse.cli import main
from seu_pulse.config import Config
from seu_pulse.models import CollectedNotice, convert_notice, notice_hash
from seu_pulse.service import PulseService
from .test_analysis import BODY, FakeClient, NOTICE, NOW
from .test_models_storage import SOURCE


def analyzed(notice=NOTICE, client=None):
    analyzer = AnalysisService(Mock(get_notice=Mock(return_value=notice)),
                               client=client or FakeClient(), clock=lambda: NOW)
    result = analyzer.analyze_notice(NOTICE.id)
    return result, {"input_snapshot": analyzer.input_snapshot, "source_snapshot": analyzer.source_snapshot}


class AnalysisStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "analysis.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_analysis_round_trip_contains_input_and_actual_model(self):
        result, snapshots = analyzed()
        with AnalysisStore(self.path, clock=lambda: NOW) as store:
            saved = store.save(result, **snapshots)
            self.assertIsInstance(saved, NoticeAnalysis)
            self.assertEqual(saved.analysis_id, saved.attempt_id)
            self.assertEqual(saved.input_snapshot["notice"]["content"], BODY)
            self.assertEqual(saved.source_snapshot["content_hash"], NOTICE.content_hash)
            self.assertIsNone(saved.result["model_info"]["model_version"])
            self.assertEqual(saved.result["model_info"]["returned_model"], "fixture-returned-model")
            identifier = saved.analysis_id
            saved.result["analysis"] = None
            self.assertIsNotNone(store.get(identifier).result["analysis"])
        with AnalysisStore(self.path, read_only=True) as store:
            self.assertEqual(store.get(identifier).result, result)

    def test_repeated_analysis_appends_and_versions_remain_separate(self):
        first, snapshots = analyzed()
        revised = replace(NOTICE, content=BODY + " 更新正文。")
        revised.content_hash = notice_hash(revised)
        changed, later_snapshots = analyzed(revised)
        with AnalysisStore(self.path) as store:
            a = store.save(first, **snapshots)
            b = store.save(first, **snapshots)
            c = store.save(changed, **later_snapshots)
            self.assertEqual(len({a.analysis_id, b.analysis_id, c.analysis_id}), 3)
            rows = store.list_records(notice_id=NOTICE.id)
            self.assertEqual(len(rows), 3)
            self.assertEqual({r.source_snapshot["content_hash"] for r in rows}, {NOTICE.content_hash, revised.content_hash})

    def test_failed_attempt_is_never_a_notice_analysis(self):
        result, snapshots = analyzed(client=FakeClient([{}, {}]))
        with AnalysisStore(self.path) as store:
            saved = store.save(result, **snapshots)
            self.assertIsInstance(saved, AnalysisAttempt)
            self.assertNotIsInstance(saved, NoticeAnalysis)
            self.assertIsNone(saved.analysis_id)
            self.assertEqual(store.list_records(), [])
            self.assertEqual(len(store.list_records(include_failed=True)), 1)
            self.assertEqual(store.connection.execute("SELECT count(*) FROM notice_analyses").fetchone()[0], 0)
            with self.assertRaises(sqlite3.IntegrityError):
                store.connection.execute("""INSERT INTO notice_analyses VALUES
                    (?,?,'success','h','h','h','h','p','m',NULL,NULL,'2026-11-01')""", (saved.attempt_id, NOTICE.id))

    def test_missing_notice_attempt_keeps_unknown_snapshots_null(self):
        result, snapshots = analyzed(None)
        with AnalysisStore(self.path) as store:
            saved = store.save(result, **snapshots)
            self.assertIsNone(saved.input_snapshot)
            self.assertIsNone(saved.source_snapshot)
            self.assertEqual(saved.result["error"]["code"], "notice_not_found")

    def test_partial_output_is_saved_as_partial(self):
        missing = replace(NOTICE, content=None)
        missing.content_hash = notice_hash(missing)
        result, snapshots = analyzed(missing, FakeClient([OUTPUT_EXAMPLE]))
        with AnalysisStore(self.path) as store:
            saved = store.save(result, **snapshots)
            self.assertIsInstance(saved, NoticeAnalysis)
            self.assertEqual(saved.result["status"], "insufficient_information")
            self.assertIsNotNone(saved.analysis_id)

    def test_malformed_success_hashes_evidence_urgency_and_time_are_rejected(self):
        result, snapshots = analyzed()
        variants = []
        for field, value in (("input_hash", "bad"), ("preferences_hash", "bad"),
                             ("notice_content_hash", "bad"), ("urgency", []),
                             ("analyzed_at", "2026-11-01T00:00:00+08:00"), ("as_of", None)):
            bad = deepcopy(result)
            bad[field] = value
            variants.append(bad)
        bad = deepcopy(result)
        bad["analysis"]["importance"]["evidence"][0]["quote"] = "fabricated"
        variants.append(bad)
        with AnalysisStore(self.path) as store:
            for bad in variants:
                with self.subTest(field=bad), self.assertRaises(ValueError):
                    store.save(bad, **snapshots)
            self.assertEqual(store.list_records(include_failed=True), [])

    def test_fake_success_with_failed_or_hidden_input_is_rejected(self):
        result, snapshots = analyzed()
        failed = deepcopy(result)
        failed.update(status="failed", error={"code": "fixture", "message": "fixture"})
        hidden = deepcopy(snapshots)
        hidden["input_snapshot"]["notice"]["content"] = None
        with AnalysisStore(self.path) as store:
            with self.assertRaises(ValueError):
                store.save(failed, **snapshots)
            with self.assertRaises(ValueError):
                store.save(result, **hidden)

    def test_atomic_failure_rolls_back_the_attempt(self):
        result, snapshots = analyzed()
        with AnalysisStore(self.path) as store:
            store.connection.executescript("""CREATE TRIGGER fixture_failure BEFORE INSERT ON notice_analyses
                BEGIN SELECT RAISE(ABORT,'fixture failure'); END;""")
            with self.assertRaises(sqlite3.IntegrityError):
                store.save(result, **snapshots)
            self.assertEqual(store.list_records(include_failed=True), [])

    def test_read_only_queries_do_not_write_or_create_files(self):
        result, snapshots = analyzed()
        with AnalysisStore(self.path) as store:
            identifier = store.save(result, **snapshots).attempt_id
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with AnalysisStore(self.path, read_only=True) as store:
            with self.assertRaises(ValueError):
                store.save(result, **snapshots)
            self.assertIsNotNone(store.get(identifier))
            self.assertIsNone(store.get("missing"))
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())
        missing = self.path.parent / "missing.db"
        with self.assertRaises(sqlite3.Error):
            AnalysisStore(missing, read_only=True)
        self.assertFalse(missing.exists())

    def test_notice_database_is_refused_without_modification(self):
        config = Config(self.path, "https://example.test", (SOURCE,))
        with PulseService(config):
            pass
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            AnalysisStore(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_read_detects_tampered_saved_payload(self):
        result, snapshots = analyzed()
        with AnalysisStore(self.path) as store:
            identifier = store.save(result, **snapshots).attempt_id
            result["input_hash"] = "invalid"
            with store.connection:
                store.connection.execute("UPDATE analysis_attempts SET result_json=? WHERE attempt_id=?",
                                         (json.dumps(result), identifier))
            with self.assertRaises(ValueError):
                store.get(identifier)
        # A separate corruption of the relational index must also be rejected.
        with AnalysisStore(self.path) as store:
            clean, snapshots = analyzed()
            identifier = store.save(clean, **snapshots).attempt_id
            with store.connection:
                store.connection.execute("UPDATE notice_analyses SET input_hash='tampered' WHERE analysis_id=?", (identifier,))
            with self.assertRaises(ValueError):
                store.get(identifier)

    def test_cli_save_and_queries_preserve_original_and_do_not_require_config_to_read(self):
        notices_path = self.path.parent / "notices.db"
        config = Config(notices_path, "https://example.test", (SOURCE,))
        with PulseService(config) as service:
            identity, notice = convert_notice(CollectedNotice(NOTICE.title, content=BODY), "test", "来源分类", NOW)
            with service.storage.connection:
                service.storage.upsert(identity, notice)
        before = notices_path.read_bytes()
        with patch("seu_pulse.cli.PulseService.from_config", return_value=PulseService(config, read_only=True)), \
                patch("seu_pulse.cli.DeepSeekClient", return_value=FakeClient()):
            output = StringIO()
            with redirect_stdout(output):
                code = main(["analyze", NOTICE.id, "--save", "--analysis-db", str(self.path), "--as-of", NOW.isoformat()])
            self.assertEqual(code, 0)
            receipt = json.loads(output.getvalue())["storage"]
            self.assertEqual(receipt["status"], "success")
        self.assertEqual(before, notices_path.read_bytes())
        for command in (["analysis-list"], ["analysis-get", receipt["attempt_id"]]):
            with patch("seu_pulse.cli.PulseService.from_config", side_effect=AssertionError("No notice read")):
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main([*command, "--analysis-db", str(self.path)]), 0)
                self.assertIn(BODY, output.getvalue())
