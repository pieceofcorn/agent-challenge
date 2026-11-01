"""Model-owned output schema and evidence validation; no network or persistence."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
import re


class AnalysisValidationError(ValueError):
    """Messages contain schema paths only, never untrusted model text."""


def obj(**properties):
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def nullable(schema):
    return {**schema, "type": [schema["type"], "null"]}


TEXT = {"type": "string", "minLength": 1}
EVIDENCE_FIELDS = ("notice.title", "notice.summary", "notice.content",
                   "preferences.interests", "preferences.keywords", "preferences.focus_areas")
EVIDENCE = obj(field={"type": "string", "enum": list(EVIDENCE_FIELDS)}, quote=TEXT)
EVIDENCES = {"type": "array", "items": EVIDENCE}
POINT = obj(date=nullable(TEXT), time=nullable(TEXT), utc_offset=nullable(TEXT))
TIME_RANGE = obj(raw_text=TEXT, start=nullable(POINT), end=nullable(POINT), evidence=EVIDENCES)
LOCATION = obj(mode={"type": ["string", "null"], "enum": ["online", "offline", "hybrid", None]},
               name=nullable(TEXT), evidence=EVIDENCES)


def decision(kind, values):
    return obj(value={"type": [kind, "null"], "enum": [*values, None]},
               reason=TEXT, evidence=EVIDENCES)


MODEL_OUTPUT_SCHEMA = obj(
    category=decision("string", ["competition", "lecture", "research", "activity",
                                 "academic_affairs", "exchange", "scholarship", "other"]),
    importance=decision("string", ["high", "medium", "low"]),
    relevance=decision("string", ["high", "medium", "low"]),
    action_required=decision("boolean", [True, False]),
    events=nullable({"type": "array", "items": obj(
        label=TEXT, time=nullable(TIME_RANGE), location=nullable(LOCATION), evidence=EVIDENCES)}),
    registration_deadlines=nullable({"type": "array", "items": obj(
        label=TEXT, raw_text=TEXT, at=nullable(POINT), evidence=EVIDENCES)}),
    limitations={"type": "array", "items": obj(field=TEXT, reason=TEXT)},
)


def fail(path, hint=None):
    suffix = f"；{hint}" if hint else ""
    raise AnalysisValidationError(f"不符合分析契约: {path}{suffix}")


def validate_shape(value, schema, path="$"):
    kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    matches = {"null": value is None, "string": type(value) is str,
               "boolean": type(value) is bool, "array": type(value) is list,
               "object": type(value) is dict}
    if not any(matches.get(k, False) for k in kinds):
        fail(path, "要求类型 " + "/".join(kinds))
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        fail(path)
    if value is None:
        return
    if type(value) is str and not value.strip():
        fail(path)
    if type(value) is dict:
        if set(value) != set(schema["properties"]):
            fail(path + ".fields", "必需且仅允许字段 " + ",".join(schema["properties"]))
        for key, child in schema["properties"].items():
            validate_shape(value[key], child, path + "." + key)
    if type(value) is list:
        if len(value) > 40:
            fail(path + ".length")
        for index, child in enumerate(value):
            validate_shape(child, schema["items"], f"{path}[{index}]")


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail("$.duplicate_key")
            result[key] = value
        return result

    def constant(_):
        fail("$.nonfinite")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, AnalysisValidationError):
            raise
        fail("$.json")


def evidence_text(items, context, path):
    if not items:
        fail(path + ".evidence")
    quotes = []
    for item in items:
        section, key = item["field"].split(".")
        value = (context.get(section) or {}).get(key)
        values = value if isinstance(value, list) else [value]
        if not any(isinstance(v, str) and item["quote"] in v for v in values):
            fail(path + ".evidence.quote")
        quotes.append(item["quote"])
    return "\n".join(quotes)


def supported_dates(text):
    result = set()
    pattern = r"(?<!\d)(\d{4})[年/.\-](\d{1,2})[月/.\-](\d{1,2})(?:日)?(?!\d)"
    for year, month, day in re.findall(pattern, text):
        try:
            result.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            continue
    return result


def supported_times(text):
    result = set()
    for hour, minute, second in re.findall(r"(?<!\d)(\d{1,2})[:：](\d{2})(?:[:：](\d{2}))?(?!\d)", text):
        try:
            parsed = time(int(hour), int(minute), int(second or 0))
            result.add(parsed.isoformat(timespec="seconds" if second else "minutes"))
        except ValueError:
            continue
    return result


def supported_offsets(text):
    result = set(re.findall(r"[+-]\d{2}:\d{2}", text))
    for sign, hour, minute in re.findall(r"(?:UTC|GMT)\s*([+-])(\d{1,2})(?::(\d{2}))?", text):
        result.add(f"{sign}{int(hour):02d}:{int(minute or 0):02d}")
    if "北京时间" in text or "中国标准时间" in text:
        result.add("+08:00")
    if re.search(r"\bUTC\b(?!\s*[+-])|\bGMT\b(?!\s*[+-])", text):
        result.add("Z")
    return result


def point_instant(point):
    if point is None or any(point[k] is None for k in ("date", "time", "utc_offset")):
        return None
    return datetime.fromisoformat(
        point["date"] + "T" + point["time"] + point["utc_offset"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def validate_point(point, raw, path):
    if point is None:
        return
    try:
        if point["date"] is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", point["date"]):
                fail(path + ".date")
            date.fromisoformat(point["date"])
            if point["date"] not in supported_dates(raw):
                fail(path + ".date.evidence", "当前 raw_text 须有完整年月日，否则 date=null")
        if point["time"] is not None:
            if not re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", point["time"]):
                fail(path + ".time")
            time.fromisoformat(point["time"])
            if point["time"] not in supported_times(raw):
                fail(path + ".time.evidence", "当前 raw_text 须有数字 H:mm[:ss]，否则 time=null")
        offset = point["utc_offset"]
        if offset is not None:
            if offset != "Z" and not re.fullmatch(r"[+-]\d{2}:\d{2}", offset):
                fail(path + ".utc_offset")
            if offset != "Z":
                hour, minute = map(int, offset[1:].split(":"))
                if hour >= 24 or minute >= 60:
                    fail(path + ".utc_offset")
                timezone(timedelta(minutes=(hour * 60 + minute) * (-1 if offset[0] == "-" else 1)))
            if offset not in supported_offsets(raw):
                fail(path + ".utc_offset.evidence")
        point_instant(point)
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, AnalysisValidationError):
            raise
        fail(path + ".calendar")


def validate_analysis(value, context):
    validate_shape(value, MODEL_OUTPUT_SCHEMA)
    for field in ("category", "importance", "relevance", "action_required"):
        item = value[field]
        if item["evidence"]:
            evidence_text(item["evidence"], context, field)
        if item["value"] is not None:
            evidence_text(item["evidence"], context, field)
            fields = [e["field"] for e in item["evidence"]]
            if not any(f.startswith("notice.") for f in fields):
                fail(field + ".notice_evidence")
            if field == "relevance":
                if not context.get("preferences") or not any(f.startswith("preferences.") for f in fields):
                    fail(field + ".preferences")
            elif any(f.startswith("preferences.") for f in fields):
                fail(field + ".content_only")
    for index, event in enumerate(value["events"] or []):
        path = f"events[{index}]"
        evidence_text(event["evidence"], context, path)
        span = event["time"]
        if span is not None:
            text = evidence_text(span["evidence"], context, path + ".time")
            if not any(span["raw_text"] in e["quote"] for e in span["evidence"]):
                fail(path + ".time.raw_text", "raw_text 须完整包含在本对象一条 evidence.quote 中")
            validate_point(span["start"], span["raw_text"], path + ".time.start")
            validate_point(span["end"], span["raw_text"], path + ".time.end")
            start, end = point_instant(span["start"]), point_instant(span["end"])
            if start is not None and end is not None and end < start:
                fail(path + ".time.order")
        location = event["location"]
        if location is not None:
            text = evidence_text(location["evidence"], context, path + ".location")
            if location["name"] is not None and location["name"] not in text:
                fail(path + ".location.name")
    for index, deadline in enumerate(value["registration_deadlines"] or []):
        path = f"registration_deadlines[{index}]"
        text = evidence_text(deadline["evidence"], context, path)
        if not any(deadline["raw_text"] in e["quote"] for e in deadline["evidence"]):
            fail(path + ".raw_text", "raw_text 须完整包含在本对象一条 evidence.quote 中")
        validate_point(deadline["at"], deadline["raw_text"], path + ".at")
    return value
