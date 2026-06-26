from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import event_factor_channel, safe_json_mapping


FAILURE_STATUSES = {"failed", "failure", "error", "timeout", "cancelled", "canceled"}
SUCCESS_STATUSES = {"success", "succeeded", "ok", "completed", "done"}
EXIT_CODE_RE = re.compile(r"\b(?:exit code|exit_code|returncode|Process exited with code)\s*[:=]?\s*(-?\d+)\b", re.I)

OFFICIAL_TOOL_FAILURE_FREQUENCY_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.tool-failure-frequency",
    "version": "v0.1.0",
    "title": "Tool failure frequency",
    "summary": "统计哪些工具调用失败最多，并用图表展示失败次数分布。",
    "title_i18n": {
        "zh-CN": "工具失败频率",
        "en-US": "Tool failure frequency",
    },
    "summary_i18n": {
        "zh-CN": "统计哪些工具调用失败最多，并用图表展示失败次数分布。",
        "en-US": "Counts which tool calls fail most often and shows the failure frequency distribution.",
    },
    "compatibility": {"evozeus_protocol": ">=0.1.0"},
    "governance": {"owner": "evozeus-factor-maintainers"},
    "input_contract": {
        "event_model": "SessionEvent[]",
        "required_fields": ["events[].id", "events[].role", "events[].text"],
        "accepted_input_kinds": ["session", "project", "scan_record_set"],
        "target_types": ["session", "project", "scan_record_set"],
        "record_types": ["session_envelope"],
        "prior_result_policy": "not_required",
    },
    "evidence_contract": {
        "ref_format": "event:<event-id>",
        "privacy": "Official factors must use redacted tool output and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["scores", "statistics", "datasets", "presentations", "evidence_refs"],
        "dataset_semantic_types": ["frequency_distribution"],
        "presentation_components": ["builtin.bar_chart.v1", "builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "tool failures by tool name",
            "input": "factors/tool-failure-frequency/session.json",
            "expected_status": "matched",
        }
    ],
}


class ToolFailureFrequencyFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_TOOL_FAILURE_FREQUENCY_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        counts: Counter[str] = Counter()
        evidence_by_tool: dict[str, list[str]] = defaultdict(list)

        for event in context.get("events", []):
            if event.get("role") != "tool":
                continue
            if event_factor_channel(event) not in {"tool_result", "tool_usage"}:
                continue
            if not _is_failed_tool_event(event):
                continue
            tool_name = _real_tool_name(event)
            if not tool_name:
                continue
            counts[tool_name] += 1
            evidence_by_tool[tool_name].append(str(event.get("id", "")))

        if not counts:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        records = [
            {
                "tool_name": tool_name,
                "count": int(count),
                "evidence_count": int(count),
                "sample_event_ids": [event_id for event_id in evidence_by_tool[tool_name] if event_id][:5],
            }
            for tool_name, count in counts.most_common()
        ]
        evidence_refs = [
            {"ref_id": event_id, "kind": "tool_event"}
            for event_ids in evidence_by_tool.values()
            for event_id in event_ids
            if event_id
        ]

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.8,
            tags=[{"type": "tool_failure", "value": "frequency"}],
            scores={"tool_failure_count": float(sum(counts.values()))},
            statistics={"top_tool": records[0]["tool_name"], "tool_count": len(records)},
            datasets=[
                {
                    "id": "tool_failure_frequency",
                    "semantic_type": "frequency_distribution",
                    "shape": "record_set",
                    "primary_key": "tool_name",
                    "records": records,
                    "schema": {
                        "tool_name": "string",
                        "count": "number",
                        "evidence_count": "number",
                    },
                }
            ],
            presentations=[
                {
                    "id": "tool_failure_bar_chart",
                    "title": "Tool failure frequency",
                    "component_ref": "builtin.bar_chart.v1",
                    "data_ref": "tool_failure_frequency",
                    "bindings": {"x": "tool_name", "y": "count"},
                    "routes": ["dashboard", "drawer"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 90,
                }
            ],
            evidence_refs=evidence_refs,
        )


def _is_failed_tool_event(event: Mapping[str, Any]) -> bool:
    tool_result = safe_json_mapping(event.get("tool_result"))
    text_result = safe_json_mapping(event.get("text"))
    if text_result:
        tool_result = {**text_result, **dict(tool_result)}

    text = str(event.get("text") or "")
    wrapper_output = _is_wrapper_output(event)
    match = EXIT_CODE_RE.search(text)
    if match:
        try:
            return int(match.group(1)) != 0
        except ValueError:
            return False

    status = str(tool_result.get("status") or tool_result.get("state") or "").lower()
    if status in FAILURE_STATUSES:
        return True
    if status in SUCCESS_STATUSES and not wrapper_output:
        return False

    for key in ("exit_code", "exitCode", "returncode", "code"):
        if key not in tool_result:
            continue
        try:
            code = int(tool_result[key])
            return code != 0
        except (TypeError, ValueError):
            continue

    stderr = str(tool_result.get("stderr") or tool_result.get("error") or "")
    if stderr.strip() and status not in SUCCESS_STATUSES:
        return True
    return False


def _real_tool_name(event: Mapping[str, Any]) -> str:
    tool_name = str(event.get("tool_name") or "")
    if _is_wrapper_output(event):
        tool_result = safe_json_mapping(event.get("tool_result"))
        return str(
            tool_result.get("name")
            or tool_result.get("tool_name")
            or event.get("function_name")
            or event.get("call_name")
            or "unknown_tool"
        )
    return tool_name or "unknown_tool"


def _is_wrapper_output(event: Mapping[str, Any]) -> bool:
    tool_name = str(event.get("tool_name") or "")
    event_type = str(event.get("codex_event_type") or "")
    return tool_name in {"function_call_output", "custom_tool_call_output"} or event_type in {
        "function_call_output",
        "custom_tool_call_output",
    }
