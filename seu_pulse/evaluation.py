"""Conservative, deterministic baseline and explicitly reviewed-reference scoring."""
from __future__ import annotations

from copy import deepcopy
import json
import re

from .analysis import OUTPUT_EXAMPLE, validate_preferences
from .analysis_models import supported_dates, supported_offsets, supported_times, validate_analysis


def rule_baseline(context):
    """Use exactly the visible snapshot, never fetch a body, preference or model."""
    validate_preferences(context["preferences"])
    output = deepcopy(OUTPUT_EXAMPLE)
    output["limitations"] = [{"field": "baseline", "reason": "固定关键词与单句时间规则，未识别的信息保持未知"}]
    fields = [("notice." + key, context["notice"].get(key) or "") for key in ("title", "summary", "content")]

    def find(words):
        return next(({"field": field, "quote": word} for field, text in fields for word in words if word in text), None)

    def set_decision(name, value, evidence):
        output[name] = {"value": value, "reason": "简单规则命中连续原文关键词", "evidence": [evidence]}

    for category, words in (
        ("competition", ("竞赛", "大赛")), ("scholarship", ("奖学金", "助学金")),
        ("lecture", ("讲座", "说明会", "报告会")),
        ("exchange", ("留学", "访学", "出国", "联合培养", "国际交流", "牛津", "剑桥")),
        ("activity", ("活动", "志愿", "招募")),
        ("academic_affairs", ("选拔", "复试", "录取", "公示", "教学", "任免", "交通管制")),
        ("research", ("科研", "研究项目")),
    ):
        evidence = find(words)
        if evidence:
            set_decision("category", category, evidence)
            break
    for level, words in (("high", ("必须", "不得", "取消资格", "逾期")),
                         ("medium", ("报名", "申请", "选拔", "资助")),
                         ("low", ("公示", "公告"))):
        evidence = find(words)
        if evidence:
            set_decision("importance", level, evidence)
            break
    evidence = find(("报名", "申请", "提交", "办理", "参加", "复试", "招募"))
    if evidence:
        set_decision("action_required", True, evidence)
    prefs = context["preferences"]
    if prefs:
        matched = next(((field, word, find((word,))) for field, words in prefs.items() for word in words
                        if find((word,))), None)
        if matched:
            field, word, evidence = matched
            output["relevance"] = {"value": "high", "reason": "显式偏好关键词在当前通知中出现",
                                   "evidence": [evidence, {"field": "preferences." + field, "quote": word}]}
        else:
            output["relevance"]["reason"] = "简单规则没有找到显式偏好匹配，不能据此断言无关"

    deadlines, events, seen = [], [], set()
    for field, text in fields:
        for raw in re.split(r"[。；;\n]", text):
            raw = raw.strip()
            if not raw or raw in seen:
                continue
            seen.add(raw)
            dates, times, offsets = supported_dates(raw), supported_times(raw), supported_offsets(raw)
            if not dates and not times and not re.search(r"\d+月\d+日", raw):
                continue
            point = {"date": next(iter(dates)) if len(dates) == 1 else None,
                     "time": next(iter(times)) if len(times) == 1 else None,
                     "utc_offset": "Z" if offsets == {"Z", "+00:00"} else (
                         next(iter(offsets)) if len(offsets) == 1 else None)}
            evidence = [{"field": field, "quote": raw}]
            if (any(w in raw for w in ("报名", "申请")) and any(w in raw for w in ("截止", "截至", "之前"))
                    and not any(w in raw for w in ("公示", "异议", "申诉"))):
                deadlines.append({"label": "规则识别的报名截止", "raw_text": raw, "at": point, "evidence": evidence})
            elif any(w in raw for w in ("讲座", "说明会", "面试", "复试", "活动时间")):
                events.append({"label": "规则识别的活动", "time": {"raw_text": raw, "start": point,
                               "end": None, "evidence": evidence}, "location": None, "evidence": evidence})
    output["registration_deadlines"] = deadlines[:40] or None
    output["events"] = events[:40] or None
    return validate_analysis(output, context)


def path_value(value, path):
    for name in path.split("."):
        if isinstance(value, list) and name.isdigit():
            value = value[int(name)] if int(name) < len(value) else None
        elif isinstance(value, dict):
            value = value.get(name)
        else:
            return None
    return value


def score_analysis(analysis, reference):
    """Never treat an automated draft or absent labels as human ground truth."""
    reviewer = reference.get("reviewer")
    if reference.get("review_status") != "approved" or not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("参考尚未由人工核对签审，不能计算正确率")
    scores = {}
    for path, accepted in reference.get("accepted_values", {}).items():
        if path not in {"category.value", "importance.value", "relevance.value", "action_required.value"}:
            raise ValueError("标量参考字段无效，时间应使用独立时间点参考")
        if not isinstance(accepted, list) or not accepted:
            raise ValueError("人工参考须给出非空可接受值列表")
        actual = path_value(analysis, path)
        scores[path] = analysis is not None and any(type(actual) is type(v) and actual == v for v in accepted)
    for path in reference.get("must_be_unknown", []):
        if not re.fullmatch(r"(?:category|importance|relevance|action_required)\.value|"
                            r"registration_deadlines\.\d+\.at\.(?:date|time|utc_offset)|"
                            r"events\.\d+\.(?:time\.(?:start|end)\.(?:date|time|utc_offset)|location\.(?:mode|name))", path):
            raise ValueError("未知字段参考路径无效")
        scores["unknown:" + path] = analysis is not None and path_value(analysis, path) is None
    for label, field in (("deadline_points", "registration_deadlines"), ("event_points", "events")):
        if label not in reference:
            continue
        values = analysis[field] if analysis else None
        actual = (None if values is None else [v["at"] for v in values] if label == "deadline_points"
                  else [None if v["time"] is None else {k: v["time"][k] for k in ("start", "end")} for v in values])
        def normalize(value):
            if isinstance(value, dict):
                return {k: ("Z" if k == "utc_offset" and v == "+00:00" else normalize(v)) for k, v in value.items()}
            if isinstance(value, list):
                return [normalize(v) for v in value]
            return value

        canonical = lambda value: sorted(json.dumps(normalize(v), sort_keys=True) for v in value) if isinstance(value, list) else value
        scores[label] = analysis is not None and canonical(actual) == canonical(reference[label])
    return {"available": analysis is not None, "fields": scores}


def score_tools(trace, reference):
    reviewer = reference.get("reviewer")
    if reference.get("review_status") != "approved" or not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("工具必要性参考未签审")
    calls = trace["tool_calls"]
    used = {c["tool"] for c in calls}
    allowed, required = reference.get("allowed_tools"), reference.get("required_tools")
    if allowed is not None and required is not None:
        if (not isinstance(allowed, list) or not isinstance(required, list)
                or not set(required) <= set(allowed) <= {"get_notice_detail", "get_user_preferences"}):
            raise ValueError("工具必要性参考无效")
    necessity = None if allowed is None or required is None else used <= set(allowed) and set(required) <= used
    mechanics = all(c["result_hash"] is not None and c["feedback_request"] is not None
                    and (c["executed"] or c["cached"]) for c in calls)
    return {"necessity": necessity, "observed_execution_and_feedback": mechanics}
