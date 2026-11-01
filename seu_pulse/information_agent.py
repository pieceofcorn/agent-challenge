"""Single-agent entry point; no persistence and no additional data collection."""
from __future__ import annotations

from pathlib import Path

from .agent_tools import AgentLimits, ToolRun
from .analysis import AnalysisService, load_preferences
from .models import digest
from .service import PulseService


class InformationAgent(AnalysisService):
    def analyze_notice(self, notice_id, *, preferences_path=None, initial_detail=False,
                       initial_preferences=False, limits=None, as_of=None):
        limits = limits or AgentLimits()
        if not isinstance(limits, AgentLimits):
            raise ValueError("limits 必须为 AgentLimits")
        path = Path(preferences_path) if preferences_path is not None else None
        # Existence is only an availability hint; the content is read after a model request.
        available = path is not None and path.exists()
        preference_reader = lambda: load_preferences(path)

        def detail_reader():
            if isinstance(self.notices, PulseService):
                with PulseService(self.notices.config, read_only=True) as reader:
                    return reader.get_notice(notice_id)
            # Trusted in-memory adapters used by synthetic checks and deterministic tests.
            return self.notices.get_notice(notice_id)

        runs = []

        def factory(context, content_hash):
            run = ToolRun(context, content_hash, detail_reader, preference_reader,
                          preferences_available=available, initial_detail=initial_detail,
                          initial_preferences=initial_preferences, limits=limits)
            runs.append(run)
            return run

        result = self._analyze_notice(notice_id, preferences=(preference_reader() if initial_preferences else None),
                                      as_of=as_of, tool_run_factory=factory)
        if runs:
            run = runs[0]
            result["input_hash"] = digest(run.context)
            result["preferences_hash"] = digest(run.context["preferences"])
            result["warnings"] = [w for w in result["warnings"] if w not in {"missing_content", "missing_preferences"}]
            if not run.context["notice"]["content"]:
                result["warnings"].append("missing_content")
            prefs = run.context["preferences"]
            if not prefs or not any(prefs.values()):
                result["warnings"].append("missing_preferences")
            result["warnings"].extend(sorted({"tool_" + c["status"] for c in run.trace["tool_calls"]
                                              if c["status"] not in {"ok", "requested"}}))
            run.trace["termination_reason"] = (result["error"]["code"] if result["error"] else result["status"])
            result["agent_trace"] = run.trace
        else:
            result["agent_trace"] = {"trace_version": "1", "initial_input_hash": None,
                                     "initial_availability": None, "limits": vars(limits), "model_steps": [],
                                     "tool_calls": [], "termination_reason": result["error"]["code"]}
        return result
