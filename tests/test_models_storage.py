from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from seu_pulse.config import SourceConfig
from seu_pulse.models import (CollectedNotice, Notice, canonical_url, convert_notice,
                              iso_utc, parse_published)
from seu_pulse.storage import Storage


NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
SOURCE = SourceConfig("test", "测试", "rsshub", "https://example.edu.cn/list.htm", route="/seu/cse/tzgg", interval_seconds=0)


class ModelTests(unittest.TestCase):
    def test_dates_keep_timezone_or_null(self):
        for raw in (None, "", "2026-10-19", "2026-10-19 12:00:00", "yesterday", "nonsense"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_published(raw))
        self.assertEqual(parse_published("Mon, 19 Oct 2026 09:30:00 +0800"),
                         "2026-10-19T01:30:00.000000+00:00")
        self.assertEqual(parse_published("2026-10-19T01:30:00Z"),
                         parse_published("2026-10-19T09:30:00+08:00"))
        with self.assertRaises(ValueError):
            iso_utc(datetime(2026, 10, 20))

    def test_url_identity_normalization(self):
        self.assertEqual(canonical_url("HTTPS://EXAMPLE.EDU.CN:443/a?b=2&utm_source=x&a=1#top"),
                         "https://example.edu.cn/a?a=1&b=2")
        for url in (None, "javascript:alert(1)", "file:///etc/passwd", "https://user:pass@example.test/", "https://example.test:bad/"):
            self.assertIsNone(canonical_url(url))

    def test_identity_separate_from_content_hash(self):
        first = convert_notice(CollectedNotice("Title", "https://example.edu.cn/a", content="old"), "test", "通知", NOW)[1]
        later = convert_notice(CollectedNotice("Revised", "https://example.edu.cn/a#top", content="new"), "test", "通知", NOW + timedelta(days=1))[1]
        self.assertEqual(first.id, later.id)
        self.assertNotEqual(first.content_hash, later.content_hash)
        repeated = convert_notice(CollectedNotice("Title", "https://example.edu.cn/a", content=" old ", metadata={"noise": 1}), "test", "通知", NOW + timedelta(days=2))[1]
        self.assertEqual(first.content_hash, repeated.content_hash)

    def test_fallback_guid_and_title_do_not_depend_on_body_or_date(self):
        for guid in (None, "stable"):
            first = convert_notice(CollectedNotice("Title", content="old", external_id=guid), "test", "通知", NOW)[1]
            later = convert_notice(CollectedNotice("Title", content="new", external_id=guid, published_at="2026-10-19"), "test", "通知", NOW)[1]
            self.assertEqual(first.id, later.id)
            self.assertEqual(later.metadata["raw_published_at"], "2026-10-19")
            self.assertIsNone(later.published_at)
        with self.assertRaises(ValueError):
            convert_notice(CollectedNotice("  "), "test", "通知", NOW)

    def test_v1_fields(self):
        self.assertEqual({f.name for f in fields(Notice)}, {
            "id", "source_id", "title", "url", "published_at", "first_seen_at", "fetched_at",
            "summary", "content", "category", "content_hash", "metadata"})

    def test_metadata_must_be_a_json_object(self):
        for metadata in ([], {"invalid": NOW}, {"invalid": float("nan")}):
            with self.subTest(metadata=metadata), self.assertRaises((ValueError, TypeError)):
                convert_notice(CollectedNotice("Title", metadata=metadata), "test", "通知", NOW)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "nested" / "test.db"
        self.db = Storage(self.path)
        self.db.sync_sources((SOURCE,))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def put(self, item, when=NOW, source_id="test"):
        identity, notice = convert_notice(item, source_id, "通知", when)
        with self.db.connection:
            status = self.db.upsert(identity, notice)
        return status, self.db.get(notice.id)

    def test_duplicate_update_and_missing_field_preservation(self):
        item = CollectedNotice("Title", "https://example.edu.cn/a", content="full", summary="summary", published_at="2026-10-19T10:00:00+08:00", metadata={"raw_published_at": "original"})
        status, first = self.put(item)
        self.assertEqual(status, "inserted")
        status, repeat = self.put(CollectedNotice("Title", "https://example.edu.cn/a"), NOW + timedelta(hours=1))
        self.assertEqual(status, "unchanged")
        self.assertEqual(repeat.content, "full")
        self.assertEqual(repeat.published_at, first.published_at)
        self.assertEqual(repeat.first_seen_at, first.first_seen_at)
        self.assertNotEqual(repeat.fetched_at, first.fetched_at)
        status, updated = self.put(CollectedNotice("Revised title", "https://example.edu.cn/a", content="revised"), NOW + timedelta(hours=2))
        self.assertEqual(status, "updated")
        self.assertEqual(updated.id, first.id)
        self.assertEqual(updated.first_seen_at, first.first_seen_at)
        self.assertEqual(len(self.db.list()), 1)

    def test_reopen_and_since_inclusive_order_pagination(self):
        _, first = self.put(CollectedNotice("A", "https://example.edu.cn/a"))
        _, second = self.put(CollectedNotice("B", "https://example.edu.cn/b"))
        self.db.close()
        self.db = Storage(self.path)
        rows = self.db.list(since=NOW.astimezone(timezone(timedelta(hours=8))))
        self.assertEqual([n.id for n in rows], sorted([first.id, second.id]))
        self.assertEqual(len(self.db.list(since=NOW + timedelta(microseconds=1))), 0)
        self.assertEqual(self.db.list(limit=1, offset=1)[0].id, rows[1].id)
        self.assertIsNone(self.db.get("missing"))
        with self.assertRaises(ValueError):
            self.db.list(since=datetime(2026, 10, 20))
        for kwargs in ({"limit": 0}, {"offset": -1}, {"limit": True}):
            with self.assertRaises(ValueError):
                self.db.list(**kwargs)

    def test_unique_constraint_and_source_transaction_rollback(self):
        identity, notice = convert_notice(CollectedNotice("A", "https://example.edu.cn/a"), "test", "通知", NOW)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connection:
                self.db.upsert(identity, notice)
                self.db.connection.execute("INSERT INTO notices SELECT * FROM notices")
        self.assertEqual(self.db.list(), [])
