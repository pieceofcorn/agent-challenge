"""Explicit offline fixtures; no test contacts a model provider."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
from contextlib import redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
import httpx2

from seu_pulse.analysis import AnalysisService, compute_urgency, load_preferences
from seu_pulse.analysis_models import AnalysisValidationError, strict_json, validate_analysis
from seu_pulse.cli import main
from seu_pulse.config import Config
from seu_pulse.model_client import Completion, DeepSeekClient, ModelError, load_api_key
from seu_pulse.models import CollectedNotice, convert_notice
from seu_pulse.service import PulseService
from .test_models_storage import SOURCE

NOW = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
BODY = "TEST FIXTURE 科研讲座。报名截止:2026年11月2日08:00 北京时间。地点:线上。"
NOTICE = convert_notice(CollectedNotice("TEST FIXTURE 科研讲座", content=BODY), "test", "来源分类", NOW)[1]
CONTEXT = {"notice": NOTICE.to_dict(), "preferences": None}


def evidence(field="notice.content", quote=BODY):
    return {"field": field, "quote": quote}


def decision(value, reason="TEST FIXTURE 原文依据"):
    return {"value": value, "reason": reason, "evidence": [evidence()] if value is not None else []}


def payload():
    return {
        "category": decision("lecture"), "importance": decision("medium"),
        "relevance": decision(None, "缺少显式偏好"), "action_required": decision(True),
        "events": [{"label": "科研讲座", "time": None, "location": {
            "mode": "online", "name": "线上", "evidence": [evidence()]}, "evidence": [evidence()]}],
        "registration_deadlines": [{"label": "讲座报名", "raw_text": BODY,
                                   "at": {"date": "2026-11-02", "time": "08:00", "utc_offset": "+08:00"},
                                   "evidence": [evidence()]}],
        "limitations": [{"field": "events[0].time", "reason": "原文未说明讲座开始时间"}],
    }


class FakeClient:
    provider = "test"
    model = "fixture-model"

    def __init__(self, outputs=None):
        self.outputs = iter(outputs if outputs is not None else [payload()])
        self.calls = []

    def complete(self, messages):
        self.calls.append(deepcopy(messages))
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return Completion(value if isinstance(value, str) else json.dumps(value), "fixture-returned-model")


def analyzer(client=None, notice=NOTICE):
    service = Mock()
    service.get_notice.return_value = notice
    return AnalysisService(service, client=client or FakeClient(), clock=lambda: NOW)


class OutputTests(unittest.TestCase):
    def test_valid_output_and_program_urgency(self):
        result = analyzer().analyze_notice(NOTICE.id)
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["analysis"]["relevance"]["value"])
        self.assertEqual(result["urgency"][0]["level"], "high")
        self.assertEqual(result["model_info"]["returned_model"], "fixture-returned-model")
        self.assertIsNone(result["model_info"]["model_version"])

    def test_explicit_preferences_evidence_and_absence(self):
        value = payload()
        value["relevance"] = decision("high")
        value["relevance"]["evidence"].append(evidence("preferences.interests", "科研"))
        preferences = {"interests": ["科研"], "keywords": [], "focus_areas": []}
        self.assertEqual(analyzer(FakeClient([value])).analyze_notice(
            NOTICE.id, preferences=preferences)["status"], "success")
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(value, CONTEXT)
        value["importance"]["evidence"].append(evidence("preferences.interests", "科研"))
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(value, {**CONTEXT, "preferences": preferences})

    def test_missing_body_is_partial_and_cannot_cite_missing_content(self):
        notice = replace(NOTICE, content=None)
        value = payload()
        for key in ("category", "importance", "relevance", "action_required"):
            value[key] = decision(None, "仅有标题，信息不足")
        value["events"] = value["registration_deadlines"] = None
        result = analyzer(FakeClient([value]), notice).analyze_notice(notice.id)
        self.assertEqual(result["status"], "insufficient_information")
        self.assertIsNotNone(result["analysis"])
        self.assertIsNone(result["urgency"])
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(payload(), {"notice": notice.to_dict(), "preferences": None})

    def test_invalid_json_missing_extra_enum_types_and_evidence(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', chr(96) * 3 + 'json\n{}\n' + chr(96) * 3, " "):
            with self.assertRaises(AnalysisValidationError):
                strict_json(text)
        changes = [
            lambda p: p.pop("events"), lambda p: p.update(urgency="high"),
            lambda p: p["importance"].update(value=2),
            lambda p: p["action_required"].update(value=1),
            lambda p: p["category"].update(value="新类别"),
            lambda p: p["category"].update(reason=""),
            lambda p: p["registration_deadlines"][0]["at"].update(date="2026-02-30"),
            lambda p: p["registration_deadlines"][0]["at"].update(date="2027-11-02"),
            lambda p: p["registration_deadlines"][0]["at"].update(utc_offset="+09:00"),
            lambda p: p["registration_deadlines"][0]["at"].update(time="23:59"),
            lambda p: p["registration_deadlines"][0]["evidence"][0].update(quote="编造原文"),
            lambda p: p["events"][0]["location"].update(name="编造会场"),
        ]
        for mutate in changes:
            value = payload()
            mutate(value)
            with self.assertRaises(AnalysisValidationError):
                validate_analysis(value, CONTEXT)

    def test_unknown_year_and_timezone_are_not_inferred(self):
        raw = "TEST FIXTURE 报名截止11月2日08:00。"
        value = payload()
        value["events"] = None
        for key in ("category", "importance", "action_required"):
            value[key]["evidence"] = [evidence(quote=raw)]
        value["registration_deadlines"][0].update(
            raw_text=raw, evidence=[evidence(quote=raw)],
            at={"date": None, "time": "08:00", "utc_offset": None})
        context = {"notice": {**NOTICE.to_dict(), "content": raw}, "preferences": None}
        validate_analysis(value, context)
        self.assertIsNone(compute_urgency(value["registration_deadlines"], NOW)[0]["level"])
        value["registration_deadlines"][0]["at"]["date"] = "2026-11-02"
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(value, context)

    def test_range_order_and_multiple_deadlines(self):
        raw = "TEST FIXTURE 2026年11月2日09:00 UTC，2026年11月2日10:00 UTC"
        value = payload()
        value["events"][0]["time"] = {
            "raw_text": raw, "start": {"date": "2026-11-02", "time": "10:00", "utc_offset": "Z"},
            "end": {"date": "2026-11-02", "time": "09:00", "utc_offset": "Z"},
            "evidence": [evidence(quote=raw)]}
        context = {"notice": {**NOTICE.to_dict(), "content": BODY + raw}, "preferences": None}
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(value, context)
        value["events"][0]["time"]["start"]["time"] = "09:00"
        value["events"][0]["time"]["end"]["time"] = "10:00"
        value["registration_deadlines"].append(deepcopy(value["registration_deadlines"][0]))
        validate_analysis(value, context)
        self.assertEqual(len(compute_urgency(value["registration_deadlines"], NOW)), 2)

    def test_urgency_boundaries_and_missing_precision(self):
        deadline = payload()["registration_deadlines"]
        instant = NOW + timedelta(hours=24)
        for delta, expected in ((0, "expired"), (-1, "expired"), (1, "high"),
                                (86400, "high"), (86401, "medium"),
                                (259200, "medium"), (259201, "low")):
            self.assertEqual(compute_urgency(deadline, instant - timedelta(seconds=delta))[0]["level"],
                             expected)
        for field in ("date", "time", "utc_offset"):
            missing = deepcopy(deadline)
            missing[0]["at"][field] = None
            self.assertIsNone(compute_urgency(missing, NOW)[0]["level"])
        with self.assertRaises(ValueError):
            compute_urgency(deadline, datetime(2026, 11, 1))
        self.assertIsNone(compute_urgency(None, NOW))
        self.assertEqual(compute_urgency([], NOW), [])

    def test_one_repair_and_explicit_failures(self):
        result = analyzer(FakeClient(["{}", payload()])).analyze_notice(NOTICE.id)
        self.assertEqual((result["status"], result["model_requests"]), ("success", 2))
        result = analyzer(FakeClient(["{}", "{}"])).analyze_notice(NOTICE.id)
        self.assertEqual(result["error"]["code"], "invalid_output")
        self.assertIsNone(result["analysis"])
        for code in ("model_auth", "model_network", "model_rate_limit", "model_unavailable"):
            result = analyzer(FakeClient([ModelError(code, "safe error")])).analyze_notice(NOTICE.id)
            self.assertEqual((result["status"], result["model_requests"]), ("failed", 1))
        result = analyzer(FakeClient([ModelError("model_blank", "blank"), payload()])).analyze_notice(NOTICE.id)
        self.assertEqual(result["status"], "success")

    def test_nested_schema_repair_receives_prior_answer_and_required_fields(self):
        bad = payload()
        bad["events"][0]["time"] = {"raw_text": BODY, "start": None, "end": None}
        client = FakeClient([bad, payload()])
        result = analyzer(client).analyze_notice(NOTICE.id)
        self.assertEqual(result["status"], "success")
        repair_messages = client.calls[1]
        self.assertEqual(repair_messages[-2]["role"], "assistant")
        self.assertEqual(json.loads(repair_messages[-2]["content"]), bad)
        self.assertIn("evidence", repair_messages[-1]["content"])

    def test_time_raw_text_cannot_be_assembled_from_separate_quotes(self):
        value = payload()
        value["events"][0]["time"] = {
            "raw_text": "科研\n讲座", "start": None, "end": None,
            "evidence": [evidence(quote="科研"), evidence(quote="讲座")]}
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(value, CONTEXT)

    def test_missing_notice_storage_error_and_input_limit_skip_model(self):
        client = FakeClient([])
        result = analyzer(client, notice=None).analyze_notice("missing")
        self.assertEqual(result["error"]["code"], "notice_not_found")
        self.assertEqual(client.calls, [])
        service = Mock()
        service.get_notice.side_effect = sqlite3.OperationalError("sensitive path")
        result = AnalysisService(service, client=client).analyze_notice("x")
        self.assertEqual(result["error"]["code"], "notice_read")
        result = analyzer(client, replace(NOTICE, content="x" * 65_000)).analyze_notice("x")
        self.assertEqual((result["error"]["code"], result["model_requests"]), ("input_limit", 0))

    def test_input_hash_tracks_actual_content_and_preferences_not_fetch_time(self):
        a = analyzer().analyze_notice(NOTICE.id)
        b = analyzer(notice=replace(NOTICE, fetched_at="2026-12-01T00:00:00Z")).analyze_notice(NOTICE.id)
        self.assertEqual(a["input_hash"], b["input_hash"])
        c = analyzer().analyze_notice(NOTICE.id, preferences={
            "interests": ["科研"], "keywords": [], "focus_areas": []})
        self.assertNotEqual(a["input_hash"], c["input_hash"])
        changed = analyzer(notice=replace(NOTICE, content=BODY + "新内容")).analyze_notice(NOTICE.id)
        self.assertNotEqual(a["input_hash"], changed["input_hash"])


class BoundaryTests(unittest.TestCase):
    def test_preferences_file_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "preferences.local.json"
            self.assertIsNone(load_preferences(path))
            value = {"interests": ["科研"], "keywords": [], "focus_areas": []}
            path.write_text(json.dumps(value))
            self.assertEqual(load_preferences(path), value)
            for value in ({"interests": ["科研"]},
                          {"interests": "科研", "keywords": [], "focus_areas": []},
                          {"interests": [""], "keywords": [], "focus_areas": []}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    load_preferences(path)

    def test_env_file_permissions_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            path = Path(temp) / ".env"
            with self.assertRaises(ModelError):
                load_api_key(path)
            path.write_text('DEEPSEEK_API_KEY="unit-test-value"\n')
            path.chmod(0o600)
            self.assertEqual(load_api_key(path), "unit-test-value")
            os.environ["DEEPSEEK_API_KEY"] = "environment-value"
            self.assertEqual(load_api_key(path), "environment-value")
            del os.environ["DEEPSEEK_API_KEY"]
            path.chmod(0o644)
            with self.assertRaises(ModelError):
                load_api_key(path)
            path.chmod(0o600)
            for content in ("DEEPSEEK_API_KEY=a\nDEEPSEEK_API_KEY=b\n", "DEEPSEEK_API_KEY=占位文字\n"):
                path.write_text(content)
                with self.assertRaises(ModelError):
                    load_api_key(path)

    def test_model_transport_request_and_safe_errors(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx2.Response(200, json={
                "id": "fixture-id", "object": "chat.completion", "created": 1793491200,
                "model": "returned-model", "choices": [{
                    "index": 0, "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "fixture-call", "type": "function", "function": {
                            "name": "notice_analysis", "arguments": json.dumps(payload())}}]}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}})

        client = DeepSeekClient("unit-test-value", http_transport=httpx2.MockTransport(handler))
        result = client.complete([{"role": "user", "content": "TEST FIXTURE JSON"}], context=CONTEXT)
        self.assertEqual(result.model, "returned-model")
        self.assertEqual(result.request_id, "fixture-id")
        self.assertEqual(result.requests, 1)
        self.assertEqual(str(calls[0].url), "https://api.deepseek.com/chat/completions")
        data = json.loads(calls[0].content)
        self.assertEqual(data["thinking"], {"type": "disabled"})
        self.assertNotIn("response_format", data)
        self.assertEqual(data["tools"][0]["function"]["name"], "notice_analysis")
        self.assertEqual(data["max_tokens"], 4096)
        self.assertNotIn("max_completion_tokens", data)
        self.assertFalse(data["stream"])
        for status, code in ((401, "model_auth"), (403, "model_auth"),
                             (429, "model_rate_limit"), (503, "model_http")):
            count = []

            def failure(request):
                count.append(request)
                return httpx2.Response(status, json={"error": {"message": "unit-test-value"}})

            with self.assertRaises(ModelError) as raised:
                DeepSeekClient("unit-test-value", http_transport=httpx2.MockTransport(failure)).complete([])
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn("unit-test-value", str(raised.exception))
            self.assertEqual(len(count), 1)

        def network(request):
            raise httpx2.ConnectError("unit-test-value", request=request)

        with self.assertRaises(ModelError) as raised:
            DeepSeekClient("unit-test-value", http_transport=httpx2.MockTransport(network)).complete([])
        self.assertEqual(raised.exception.code, "model_network")

    def test_blank_truncated_malformed_and_oversize_model_responses(self):
        for content, finish, expected in ((" ", "stop", "model_blank"),
                                          ("{}", "length", "model_incomplete"),
                                          ("{}", "stop", "invalid_output")):
            calls = []

            def handler(request):
                calls.append(request)
                return httpx2.Response(200, json={
                    "id": "fixture-id", "object": "chat.completion", "created": 1793491200,
                    "model": "fixture-model", "choices": [{"index": 0, "finish_reason": finish,
                        "message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

            with self.assertRaises(ModelError) as raised:
                DeepSeekClient("unit-test-value", http_transport=httpx2.MockTransport(handler)).complete([])
            self.assertEqual(raised.exception.code, expected)
            self.assertLessEqual(len(calls), 2)

        for response, expected in (
            (httpx2.Response(302, headers={"Location": "https://example.test"}), "model_redirect"),
            (httpx2.Response(200, content=b"x" * (512 * 1024 + 1)), "model_response_limit"),
        ):
            with self.assertRaises(ModelError) as raised:
                DeepSeekClient("unit-test-value", http_transport=httpx2.MockTransport(
                    lambda request: response)).complete([])
            self.assertEqual(raised.exception.code, expected)

    def test_invalid_header_key_never_reaches_transport_or_error_text(self):
        handler = Mock()
        with self.assertRaises(ModelError) as raised:
            DeepSeekClient("unit-test-value\nInjected: value",
                           http_transport=httpx2.MockTransport(handler)).complete([])
        handler.assert_not_called()
        self.assertNotIn("unit-test-value", str(raised.exception))

    def test_read_only_database_and_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "test.db"
            config = Config(database, "https://rsshub.example.test", (SOURCE,))
            with PulseService(config, collectors={}) as service:
                identity, notice = convert_notice(CollectedNotice(NOTICE.title, content=BODY), "test", "test", NOW)
                with service.storage.connection:
                    service.storage.upsert(identity, notice)
                before_export = service.export_notices()
            before_hash = hashlib.sha256(database.read_bytes()).hexdigest()
            with PulseService(config, read_only=True) as service:
                self.assertEqual(service.export_notices(), before_export)
                with self.assertRaises(ValueError):
                    service.fetch_notices()
                with self.assertRaises(sqlite3.OperationalError):
                    service.storage.connection.execute("DELETE FROM notices")
                self.assertEqual(AnalysisService(service, client=FakeClient(), clock=lambda: NOW).analyze_notice(
                    notice.id)["status"], "success")
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before_hash)
            for actual_notice, expected in ((notice, 0), (replace(notice, content=None), 4), (None, 3)):
                service = Mock()
                service.__enter__ = Mock(return_value=service)
                service.__exit__ = Mock(return_value=None)
                service.get_notice.return_value = actual_notice
                value = payload()
                if actual_notice is not notice:
                    for key in ("category", "importance", "relevance", "action_required"):
                        value[key] = decision(None)
                    value["events"] = value["registration_deadlines"] = None
                out = StringIO()
                with patch("seu_pulse.cli.PulseService.from_config", return_value=service) as factory, patch(
                    "seu_pulse.cli.DeepSeekClient", return_value=FakeClient([value])
                ), redirect_stdout(out):
                    self.assertEqual(main(["analyze", notice.id, "--as-of", NOW.isoformat()]), expected)
                factory.assert_called_once_with("config.toml", read_only=True)
                json.loads(out.getvalue())
