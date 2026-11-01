"""Framework runs against deterministic synthetic FunctionModel responses, never live API."""
from copy import deepcopy
import json
from unittest.mock import Mock, patch
import unittest

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from seu_pulse.analysis import AnalysisService
from seu_pulse.model_client import DeepSeekClient, ModelError
from .test_analysis import CONTEXT, NOTICE, NOW, payload


class FrameworkTests(unittest.TestCase):
    def run_model(self, outputs):
        calls = []
        iterator = iter(outputs)

        async def respond(messages, info):
            calls.append((deepcopy(messages), info))
            value = next(iterator)
            content = value if isinstance(value, str) else json.dumps(value)
            return ModelResponse(parts=[ToolCallPart("notice_analysis", content)], model_name="fixture-model",
                                 provider_response_id=f"fixture-{len(calls)}", finish_reason="tool_call")

        client = DeepSeekClient(agent_model=FunctionModel(respond, model_name="fixture-model"), timeout=2)
        notices = Mock()
        notices.get_notice.return_value = NOTICE
        with patch("seu_pulse.model_client.load_api_key", side_effect=AssertionError("No key access in fixtures")):
            result = AnalysisService(notices, client=client, clock=lambda: NOW).analyze_notice(NOTICE.id)
        return result, calls, client

    def test_framework_is_active_with_typed_output_and_no_application_tools(self):
        result, calls, client = self.run_model([payload()])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["framework_info"], {"name": "pydantic-ai", "version": "2.54.0"})
        self.assertEqual(result["model_requests"], 1)
        self.assertEqual(result["model_info"]["returned_model"], "fixture-model")
        self.assertEqual(calls[0][1].function_tools, [])
        self.assertEqual([tool.name for tool in calls[0][1].output_tools], ["notice_analysis"])
        self.assertEqual(len(client.last_outputs), 1)

    def test_framework_repairs_missing_nested_field_without_outer_retry_multiplication(self):
        bad = payload()
        bad["events"][0]["time"] = {"raw_text": NOTICE.content, "start": None, "end": None}
        result, calls, client = self.run_model([bad, payload()])
        self.assertEqual(result["status"], "success")
        self.assertEqual((len(calls), result["model_requests"]), (2, 2))
        self.assertIn("output_repair_attempted", result["warnings"])
        self.assertEqual(len(client.last_outputs), 2)

    def test_semantic_evidence_is_checked_inside_framework_retry(self):
        bad = payload()
        bad["importance"]["evidence"][0]["quote"] = "fabricated evidence"
        result, calls, _ = self.run_model([bad, payload()])
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(calls), 2)

    def test_invalid_output_stops_after_two_requests_and_never_becomes_analysis(self):
        result, calls, _ = self.run_model([{}, {}])
        self.assertEqual(result["error"]["code"], "invalid_output")
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["analysis"])
        self.assertEqual((len(calls), result["model_requests"]), (2, 2))

    def test_raw_json_checks_reject_duplicate_keys_and_fences_even_if_parser_can_recover(self):
        raw = json.dumps(payload())
        duplicate = raw[:-1] + ',"events":null}'
        fenced = chr(96) * 3 + "json\n" + raw + "\n" + chr(96) * 3
        for invalid in (duplicate, fenced):
            with self.subTest(kind=invalid[:10]):
                result, calls, _ = self.run_model([invalid, invalid])
                self.assertEqual(result["status"], "failed")
                self.assertEqual(len(calls), 2)

    def test_unknown_year_or_timezone_is_not_filled_by_framework(self):
        bad = payload()
        bad["registration_deadlines"][0]["at"]["utc_offset"] = "+09:00"
        result, calls, _ = self.run_model([bad, bad])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "invalid_output")
        self.assertEqual(len(calls), 2)

    def test_unregistered_tool_request_has_no_executor(self):
        calls = []

        async def respond(messages, info):
            calls.append(info)
            return ModelResponse(parts=[ToolCallPart("run_shell", {"command": "never executed"})],
                                 model_name="fixture-model", finish_reason="tool_call")

        client = DeepSeekClient(agent_model=FunctionModel(respond), timeout=2)
        with self.assertRaises(ModelError) as raised:
            client.complete([{"role": "user", "content": "TEST JSON"}], context=CONTEXT)
        self.assertIn(raised.exception.code, {"invalid_output", "model_request_limit"})
        self.assertLessEqual(len(calls), 2)
        self.assertTrue(all(info.function_tools == [] for info in calls))
