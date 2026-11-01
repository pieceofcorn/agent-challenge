"""Actual Pydantic AI loops against synthetic models and read-only local fixtures."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
from time import monotonic
import unittest
from unittest.mock import Mock, patch

import httpx2
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from seu_pulse.agent_tools import AgentLimits
from seu_pulse.analysis import OUTPUT_EXAMPLE
from seu_pulse.analysis_models import AnalysisValidationError, validate_analysis
from seu_pulse.cli import main
from seu_pulse.config import Config
from seu_pulse.information_agent import InformationAgent
from seu_pulse.model_client import DeepSeekClient
from seu_pulse.models import CollectedNotice, convert_notice
from seu_pulse.service import PulseService
from .test_analysis import BODY, NOTICE, NOW, payload
from .test_models_storage import SOURCE


def detail(call_id="detail-1", **args):
    return ToolCallPart("get_notice_detail", args or {"notice_id": NOTICE.id}, tool_call_id=call_id)


def final(value=None):
    return ToolCallPart("notice_analysis", json.dumps(value if value is not None else payload()))


class InformationAgentTests(unittest.TestCase):
    def run_agent(self, responses, *, notices=None, **options):
        calls = []
        iterator = iter(responses)

        async def respond(messages, info):
            calls.append((deepcopy(messages), info))
            return ModelResponse(parts=next(iterator), model_name="fixture-model", finish_reason="tool_call")

        notices = notices if notices is not None else Mock(get_notice=Mock(return_value=NOTICE))
        client = DeepSeekClient(agent_model=FunctionModel(respond), timeout=1)
        with patch("seu_pulse.model_client.load_api_key", side_effect=AssertionError("No live API in tests")):
            result = InformationAgent(notices, client=client, clock=lambda: NOW).analyze_notice(NOTICE.id, **options)
        return result, calls, notices

    def test_sufficient_initial_context_can_finish_without_reading_tools(self):
        result, calls, notices = self.run_agent([[final()]], initial_detail=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["agent_trace"]["tool_calls"], [])
        self.assertEqual(notices.get_notice.call_count, 1)
        self.assertEqual({t.name for t in calls[0][1].function_tools},
                         {"get_notice_detail", "get_user_preferences"})
        self.assertEqual(result["urgency"][0]["level"], "high")  # Exactly 24 hours is included.

    def test_missing_detail_executes_and_returns_to_the_same_agent(self):
        result, calls, notices = self.run_agent([[detail()], [final()]])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["model_requests"], 2)
        self.assertEqual(notices.get_notice.call_count, 2)
        initial = "".join(p.content for m in calls[0][0] for p in m.parts if isinstance(getattr(p, "content", None), str))
        self.assertNotIn(BODY, initial)
        returns = [p for m in calls[1][0] for p in m.parts if isinstance(p, ToolReturnPart)]
        self.assertEqual(returns[0].content["notice"]["content"], BODY)
        call = result["agent_trace"]["tool_calls"][0]
        self.assertTrue(call["executed"])
        self.assertEqual((call["status"], call["feedback_request"]), ("ok", 2))
        self.assertNotIn(BODY, json.dumps(result["agent_trace"]))
        self.assertNotIn("output_repair_attempted", result["warnings"])

    def test_preferences_are_read_only_on_request_and_can_ground_relevance(self):
        prefs = {"interests": ["科研"], "keywords": [], "focus_areas": []}
        output = payload()
        output["relevance"] = {"value": "high", "reason": "合成偏好匹配", "evidence": [
            {"field": "notice.content", "quote": "科研"}, {"field": "preferences.interests", "quote": "科研"}]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "preferences.local.json"
            path.write_text(json.dumps(prefs))
            with patch("seu_pulse.information_agent.load_preferences", return_value=prefs) as reader:
                result, calls, _ = self.run_agent([
                    [ToolCallPart("get_user_preferences", {}, tool_call_id="prefs-1")], [final(output)]],
                    preferences_path=path, initial_detail=True)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["analysis"]["relevance"]["value"], "high")
            self.assertEqual(result["agent_trace"]["tool_calls"][0]["feedback_request"], 2)
            self.assertNotIn(str(path), json.dumps(calls[0][0], default=str))
            self.assertNotIn("missing_preferences", result["warnings"])
            sufficient, _, _ = self.run_agent([[final(output)]], preferences_path=path,
                                               initial_detail=True, initial_preferences=True)
            self.assertEqual(sufficient["status"], "success")
            self.assertEqual(sufficient["agent_trace"]["tool_calls"], [])
            with patch("seu_pulse.information_agent.load_preferences", side_effect=AssertionError("Not requested")):
                self.run_agent([[final()]], initial_detail=True, preferences_path=path)

    def test_missing_preferences_are_not_invented(self):
        result, _, _ = self.run_agent([
            [ToolCallPart("get_user_preferences", {}, tool_call_id="prefs-1")], [final()]], initial_detail=True)
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["analysis"]["relevance"]["value"])
        self.assertEqual(result["agent_trace"]["tool_calls"][0]["status"], "missing")

    def test_hidden_body_cannot_be_cited_without_a_tool(self):
        result, calls, _ = self.run_agent([[final()], [final()]])
        self.assertEqual(result["error"]["code"], "invalid_output")
        self.assertIsNone(result["analysis"])
        self.assertEqual(len(calls), 2)

    def test_read_failures_missing_body_and_disappearing_notice_are_distinct(self):
        for second, expected in ((sqlite3.OperationalError("private-path-and-secret"), "read_error"),
                                 (None, "not_found"), (replace(NOTICE, content=None), "missing_content")):
            with self.subTest(expected=expected):
                notices = Mock(get_notice=Mock(side_effect=[NOTICE, second]))
                result, calls, _ = self.run_agent([[detail()], [final(OUTPUT_EXAMPLE)]], notices=notices)
                self.assertEqual(result["status"], "insufficient_information")
                self.assertEqual(result["agent_trace"]["tool_calls"][0]["status"], expected)
                self.assertNotIn("private-path-and-secret", json.dumps(result))
                self.assertNotIn("private-path-and-secret", str(calls))

    def test_changed_notice_version_is_not_mixed_into_analysis(self):
        notices = Mock(get_notice=Mock(side_effect=[NOTICE, replace(NOTICE, content_hash="different-version")]))
        result, _, _ = self.run_agent([[detail()], [final(OUTPUT_EXAMPLE)]], notices=notices)
        self.assertEqual(result["error"]["code"], "notice_changed")
        self.assertIsNone(result["analysis"])

    def test_bad_names_arguments_and_cross_notice_reads_never_execute(self):
        for part, code in ((ToolCallPart("run_shell", {"command": "never"}), "tool_not_allowed"),
                           (detail(notice_id="foreign-id"), "tool_arguments"),
                           (detail(notice_id=123), "tool_arguments"),
                           (detail(notice_id=NOTICE.id, path="private"), "tool_arguments"),
                           (ToolCallPart("get_user_preferences", {"path": "private"}), "tool_arguments"),
                           (ToolCallPart("get_notice_detail", '{"notice_id":"a","notice_id":"b"}'), "tool_arguments")):
            with self.subTest(code=code, part=part.tool_name):
                result, calls, notices = self.run_agent([[part]])
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(notices.get_notice.call_count, 1)
                self.assertFalse(result["agent_trace"]["tool_calls"][0]["executed"])
                self.assertEqual(len(calls), 1)
                self.assertNotIn("private", json.dumps(result["agent_trace"]))
        part = detail(call_id="private-contact-marker")
        result, _, _ = self.run_agent([[part], [final()]])
        self.assertNotIn("private-contact-marker", json.dumps(result["agent_trace"]))

    def test_batch_exceeding_tool_budget_executes_nothing(self):
        for maximum in (0, 1):
            result, _, notices = self.run_agent([[detail(), detail("detail-2")]],
                                                limits=AgentLimits(max_tool_calls=maximum))
            self.assertEqual(result["error"]["code"], "tool_call_limit")
            self.assertEqual(notices.get_notice.call_count, 1)

    def test_repeated_reads_use_cache_but_still_consume_budget(self):
        result, _, notices = self.run_agent([[detail()], [detail("detail-2")], [final()]])
        self.assertEqual(result["status"], "success")
        self.assertEqual(notices.get_notice.call_count, 2)
        self.assertTrue(result["agent_trace"]["tool_calls"][1]["cached"])
        self.assertFalse(result["agent_trace"]["tool_calls"][1]["executed"])
        result, calls, _ = self.run_agent([[detail()], [detail("detail-2")]], limits=AgentLimits(max_tool_calls=1))
        self.assertEqual(result["error"]["code"], "tool_call_limit")
        self.assertEqual(len(calls), 2)

    def test_model_request_limit_includes_tool_round_trips(self):
        result, calls, _ = self.run_agent([[detail()]], limits=AgentLimits(max_requests=1))
        self.assertEqual(result["error"]["code"], "model_request_limit")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(result["agent_trace"]["tool_calls"][0]["feedback_request"])

    def test_mixed_final_and_tool_request_cannot_bypass_feedback(self):
        result, _, notices = self.run_agent([[detail(), final()]])
        self.assertEqual(result["error"]["code"], "premature_output")
        self.assertEqual(notices.get_notice.call_count, 1)

    def test_tool_timeout_is_bounded_and_late_result_cannot_change_context(self):
        release = Event()

        def delayed():
            release.wait(2)
            return NOTICE

        notices = Mock()
        count = []

        def read(_):
            count.append(1)
            return NOTICE if len(count) == 1 else delayed()

        notices.get_notice.side_effect = read
        start = monotonic()
        try:
            result, _, _ = self.run_agent([[detail()], [final(OUTPUT_EXAMPLE)]], notices=notices,
                                         limits=AgentLimits(tool_timeout=0.02))
            self.assertLess(monotonic() - start, 1)
            self.assertEqual(result["status"], "insufficient_information")
            self.assertEqual(result["agent_trace"]["tool_calls"][0]["status"], "timeout")
        finally:
            release.set()

    def test_total_timeout_terminates_the_agent(self):
        async def slow(messages, info):
            await asyncio.sleep(1)
        client = DeepSeekClient(agent_model=FunctionModel(slow))
        notices = Mock(get_notice=Mock(return_value=NOTICE))
        result = InformationAgent(notices, client=client).analyze_notice(
            NOTICE.id, limits=AgentLimits(run_timeout=0.02))
        self.assertEqual(result["error"]["code"], "agent_timeout")
        self.assertEqual(result["agent_trace"]["termination_reason"], "agent_timeout")

    def test_real_sqlite_tools_and_cli_are_read_only_and_preserve_v1(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "notices.db"
            config = Config(path, "https://example.test", (SOURCE,))
            with PulseService(config) as service:
                identity, notice = convert_notice(CollectedNotice(NOTICE.title, content=BODY), "test", "来源分类", NOW)
                with service.storage.connection:
                    service.storage.upsert(identity, notice)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            with PulseService(config, read_only=True) as service:
                result, _, _ = self.run_agent([[detail()], [final()]], notices=service)
                self.assertEqual(result["status"], "success")
                self.assertEqual(len(service.get_notice(NOTICE.id).to_dict()), 12)
                tables = [r[0] for r in service.storage.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                self.assertNotIn("analyses", tables)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
            with patch("seu_pulse.cli.PulseService.from_config") as opened, patch("seu_pulse.cli.DeepSeekClient") as client:
                opened.return_value.__enter__.return_value.get_notice.return_value = None
                client.return_value.provider, client.return_value.model = "fixture", "fixture"
                client.return_value.framework, client.return_value.framework_version = "pydantic-ai", "2.54.0"
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["agent-analyze", "missing"]), 3)
                self.assertEqual(json.loads(output.getvalue())["model_requests"], 0)
                client.return_value.complete.assert_not_called()
                opened.assert_called_once_with("config.toml", read_only=True)

    def test_http_serialization_contains_actual_tool_return_before_final(self):
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            part = detail() if len(requests) == 1 else final()
            return httpx2.Response(200, json={"id": "fixture-response", "object": "chat.completion",
                "created": 1793491200, "model": "fixture-http", "choices": [{"index": 0,
                    "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                        "tool_calls": [{"id": part.tool_call_id, "type": "function", "function": {
                            "name": part.tool_name, "arguments": part.args_as_json_str()}}]}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40}})

        client = DeepSeekClient("unit-test-value", http_transport=httpx2.MockTransport(handler))
        result = InformationAgent(Mock(get_notice=Mock(return_value=NOTICE)), client=client).analyze_notice(NOTICE.id)
        self.assertEqual(result["status"], "success")
        tools = [m for m in requests[1]["messages"] if m["role"] == "tool"]
        self.assertEqual(json.loads(tools[0]["content"])["notice"]["content"], BODY)
        self.assertEqual(result["agent_trace"]["tool_calls"][0]["feedback_request"], 2)

    def test_invalid_preferences_oversize_detail_and_invalid_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "preferences.local.json"
            path.write_text('{"extra":"private"}')
            result, _, _ = self.run_agent([
                [ToolCallPart("get_user_preferences", {}, tool_call_id="prefs")], [final()]],
                preferences_path=path, initial_detail=True)
            self.assertEqual(result["status"], "insufficient_information")
            self.assertEqual(result["agent_trace"]["tool_calls"][0]["status"], "read_error")
        notices = Mock(get_notice=Mock(side_effect=[NOTICE, replace(NOTICE, content="x" * 64001)]))
        result, _, _ = self.run_agent([[detail()], [final(OUTPUT_EXAMPLE)]], notices=notices)
        self.assertEqual(result["agent_trace"]["tool_calls"][0]["status"], "input_limit")
        for args in ({"max_requests": 0}, {"max_tool_calls": -1}, {"tool_timeout": float("nan")}, {"run_timeout": True}):
            with self.assertRaises(ValueError):
                AgentLimits(**args)

    def test_explicit_utc_accepts_equivalent_zero_offset_without_inventing_a_zone(self):
        body = BODY.replace("北京时间", "UTC")
        context = {"notice": {"content": body}, "preferences": None}
        output = json.loads(json.dumps(payload(), ensure_ascii=False).replace("北京时间", "UTC"))
        output["registration_deadlines"][0]["at"]["utc_offset"] = "+00:00"
        self.assertEqual(validate_analysis(output, context)["registration_deadlines"][0]["at"]["utc_offset"], "+00:00")
        output["registration_deadlines"][0]["at"]["utc_offset"] = "+01:00"
        with self.assertRaises(AnalysisValidationError):
            validate_analysis(output, context)
