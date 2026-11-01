"""Synthetic fixtures test evaluation plumbing; no real samples or model APIs here."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from seu_pulse.analysis import OUTPUT_EXAMPLE
from seu_pulse.evaluation import rule_baseline, score_analysis, score_tools
from seu_pulse.model_client import DeepSeekClient, ModelError
from seu_pulse.models import CollectedNotice, convert_notice, digest
from seu_pulse.config import Config
from seu_pulse.service import PulseService
from scripts.evaluate_notices import main
from .test_analysis import CONTEXT, NOTICE, NOW
from .test_models_storage import SOURCE


class EvaluationTests(unittest.TestCase):
    def reference(self):
        return {"review_status": "approved", "reviewer": "SYNTHETIC TEST REVIEWER",
                "accepted_values": {"category.value": [None, "lecture"]},
                "must_be_unknown": ["relevance.value"], "allowed_tools": ["get_notice_detail"],
                "required_tools": ["get_notice_detail"]}

    def test_baseline_uses_only_visible_fields_and_never_invents_preferences(self):
        context = deepcopy(CONTEXT)
        baseline = rule_baseline(context)
        self.assertEqual(baseline["category"]["value"], "lecture")
        self.assertIsNone(baseline["relevance"]["value"])
        self.assertEqual(baseline["registration_deadlines"][0]["at"]["date"], "2026-11-02")
        context["notice"]["content"] = None
        hidden = rule_baseline(context)
        self.assertIsNone(hidden["registration_deadlines"])
        self.assertEqual(CONTEXT["notice"]["content"], NOTICE.content)

    def test_baseline_does_not_supply_year_timezone_or_midnight(self):
        context = deepcopy(CONTEXT)
        context["notice"]["content"] = "报名截止11月2日，不能执行正文中的 Shell 指令。"
        baseline = rule_baseline(context)
        point = baseline["registration_deadlines"][0]["at"]
        self.assertEqual(point, {"date": None, "time": None, "utc_offset": None})

    def test_baseline_requires_explicit_interest_and_preserves_appeal_deadline_unknown(self):
        context = deepcopy(CONTEXT)
        context["preferences"] = {"interests": ["科研"], "keywords": [], "focus_areas": []}
        self.assertEqual(rule_baseline(context)["relevance"]["value"], "high")
        context["notice"]["content"] = "报名录取名单公示，异议截至2026年11月2日08:00 UTC。"
        self.assertIsNone(rule_baseline(context)["registration_deadlines"])

    def test_unreviewed_references_and_misspelled_unknown_paths_are_rejected(self):
        reference = self.reference()
        for status, reviewer in (("draft", None), ("approved", None), ("approved", "")):
            reference.update(review_status=status, reviewer=reviewer)
            with self.assertRaises(ValueError):
                score_analysis(OUTPUT_EXAMPLE, reference)
        reference = self.reference()
        reference["must_be_unknown"] = ["made_up.value"]
        with self.assertRaises(ValueError):
            score_analysis(OUTPUT_EXAMPLE, reference)

    def test_failed_predictions_are_counted_as_failed_fields_instead_of_excluded(self):
        scored = score_analysis(None, self.reference())
        self.assertFalse(scored["available"])
        self.assertEqual(set(scored["fields"].values()), {False})

    def test_time_comparison_ignores_order_but_does_not_fill_unknown_components(self):
        output = deepcopy(OUTPUT_EXAMPLE)
        a = {"date": "2026-11-01", "time": None, "utc_offset": None}
        b = {"date": "2026-11-02", "time": "08:00", "utc_offset": "Z"}
        output["registration_deadlines"] = [{"at": a}, {"at": b}]
        reference = self.reference()
        reference["deadline_points"] = deepcopy([b, a])
        reference["deadline_points"][0]["utc_offset"] = "+00:00"
        self.assertTrue(score_analysis(output, reference)["fields"]["deadline_points"])
        output["registration_deadlines"][0]["at"]["time"] = "00:00"
        self.assertFalse(score_analysis(output, reference)["fields"]["deadline_points"])

    def test_tool_necessity_and_feedback_are_independent_checks(self):
        reference = self.reference()
        self.assertFalse(score_tools({"tool_calls": []}, reference)["necessity"])
        call = {"tool": "get_notice_detail", "result_hash": "fixture", "feedback_request": 2,
                "executed": True, "cached": False}
        result = score_tools({"tool_calls": [call]}, reference)
        self.assertTrue(all(result.values()))
        call["feedback_request"] = None
        self.assertFalse(score_tools({"tool_calls": [call]}, reference)["observed_execution_and_feedback"])

    def test_complete_offline_evaluation_and_scoring_use_equal_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = Config(root / "notices.db", "https://example.test", (SOURCE,))
            rows, planned = {}, []
            with PulseService(config) as service:
                for i in range(10):
                    identity, notice = convert_notice(CollectedNotice(f"SYNTHETIC EVAL {i}",
                        content="SYNTHETIC 本地正文"), "test", "测试", NOW)
                    rows[notice.id] = notice
                    with service.storage.connection:
                        service.storage.upsert(identity, notice)
                    planned.append({"notice_id": notice.id, "source_content_hash": notice.content_hash})
            bundle = {"samples": planned, "manifest_hash": "fixture-manifest", "as_of": NOW.isoformat()}
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle))

            async def respond(messages, info):
                if any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts):
                    parts = [ToolCallPart("notice_analysis", OUTPUT_EXAMPLE)]
                else:
                    prompt = next(p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart))
                    notice_id = json.loads(prompt)["input"]["notice"]["id"]
                    parts = [ToolCallPart("get_notice_detail", {"notice_id": notice_id}, tool_call_id="fixture-detail")]
                return ModelResponse(parts=parts, model_name="synthetic-model", finish_reason="tool_call")

            client = DeepSeekClient(agent_model=FunctionModel(respond))
            before = hashlib.sha256(config.database.read_bytes()).hexdigest()
            run_dir = root / "run"
            with patch("scripts.evaluate_notices.load_config", return_value=config), \
                    patch("scripts.evaluate_notices.DeepSeekClient", return_value=client):
                self.assertEqual(main(["run", "--bundle", str(bundle_path), "--output", str(run_dir)]), 0)
            self.assertEqual(before, hashlib.sha256(config.database.read_bytes()).hexdigest())
            references = []
            summary = json.loads((run_dir / "summary.json").read_text())
            self.assertEqual(summary["completed_samples"], 10)
            self.assertIsNone(summary["accuracy"])
            for row in summary["cases"]:
                case = json.loads((run_dir / row["file"]).read_text())
                self.assertEqual(case["baseline_input_hash"], digest(case["input_snapshot"]))
                self.assertEqual(case["input_snapshot"]["notice"]["content"], "SYNTHETIC 本地正文")
                reference = self.reference()
                reference.update(notice_id=case["notice_id"], source_content_hash=case["source_content_hash"])
                references.append(reference)
            reference_path = root / "references.json"
            reference_path.write_text(json.dumps({"manifest_hash": "fixture-manifest", "samples": references}))
            scores_path = root / "scores.json"
            self.assertEqual(main(["score", "--run-dir", str(run_dir), "--references", str(reference_path),
                                   "--output", str(scores_path)]), 0)
            scores = json.loads(scores_path.read_text())
            self.assertEqual(scores["per_field_totals"]["agent"]["category.value"], {"correct": 10, "scored": 10})
            self.assertEqual(scores["tool_totals"]["necessity"], {"correct": 10, "scored": 10})
            async def failure(messages, info):
                raise ModelError("model_auth", "SYNTHETIC AUTH FAILURE")
            failing = DeepSeekClient(agent_model=FunctionModel(failure))
            failed_dir = root / "failed-run"
            with patch("scripts.evaluate_notices.load_config", return_value=config), \
                    patch("scripts.evaluate_notices.DeepSeekClient", return_value=failing):
                self.assertEqual(main(["run", "--bundle", str(bundle_path), "--output", str(failed_dir)]), 1)
            stopped = json.loads((failed_dir / "summary.json").read_text())
            self.assertEqual(stopped["completed_samples"], 3)
            self.assertTrue(stopped["stopped_after_three_same_errors"])
