from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any, Iterable, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import event_factor_channel


SKILL_PATTERN = re.compile(r"(?:skill:|\$)([A-Za-z0-9_.:-]+)")
MCP_TOOL_PATTERN = re.compile(r"\bmcp__([A-Za-z0-9_:-]+)__([A-Za-z0-9_:-]+)\b")
RESOURCE_ORDER = {"tool": 0, "skill": 1, "mcp": 2, "plugin": 3, "connector": 4}


OFFICIAL_SESSION_RESOURCE_USAGE_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.session-resource-usage",
    "version": "v0.1.0",
    "title": "Session resource usage",
    "summary": "提取当前会话使用过的 tool、skill、MCP server、plugin 和 connector，并统计各自出现次数。",
    "title_i18n": {
        "zh-CN": "会话资源使用",
        "en-US": "Session resource usage",
    },
    "summary_i18n": {
        "zh-CN": "提取当前会话使用过的 tool、skill、MCP server、plugin 和 connector，并统计各自出现次数。",
        "en-US": "Extracts tools, skills, MCP servers, plugins, and connectors used in a session and counts them.",
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
        "privacy": "Official factors must use redacted event metadata and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["tags", "scores", "statistics", "datasets", "presentations", "evidence_refs"],
        "dataset_semantic_types": ["session_resource_usage", "frequency_distribution", "diagnostic_record_set"],
        "presentation_components": ["builtin.bar_chart.v1", "builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "session uses tools skills and mcp servers",
            "input": "factors/session-resource-usage/session.json",
            "expected_status": "matched",
        }
    ],
}


class SessionResourceUsageFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_SESSION_RESOURCE_USAGE_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        counts: Counter[tuple[str, str]] = Counter()
        diagnostics: Counter[tuple[str, str]] = Counter()
        evidence_by_resource: dict[tuple[str, str], list[str]] = defaultdict(list)

        for event in context.get("events", []):
            if event_factor_channel(event) == "context":
                continue
            event_id = str(event.get("id", ""))
            resources, ignored = _resources_for_event_with_diagnostics(event)
            for resource_type, resource_name in resources:
                key = (resource_type, resource_name)
                counts[key] += 1
                if event_id:
                    evidence_by_resource[key].append(event_id)
            for resource_name, reason in ignored:
                diagnostics[(resource_name, reason)] += 1

        if not counts:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        records = [
            {
                "resource_key": f"{resource_type}:{resource_name}",
                "resource_type": resource_type,
                "resource_name": resource_name,
                "count": int(count),
                "sample_event_ids": evidence_by_resource[(resource_type, resource_name)][:5],
            }
            for (resource_type, resource_name), count in sorted(
                counts.items(),
                key=lambda item: (RESOURCE_ORDER.get(item[0][0], 99), item[0][1]),
            )
        ]
        seen_event_ids: set[str] = set()
        evidence_refs = []
        for event_ids in evidence_by_resource.values():
            for event_id in event_ids:
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                evidence_refs.append({"ref_id": event_id, "kind": "event"})

        type_distribution: Counter[str] = Counter()
        for (resource_type, _), count in counts.items():
            type_distribution[resource_type] += count
        distribution_records = [
            {"resource_type": resource_type, "count": int(count)}
            for resource_type, count in sorted(type_distribution.items(), key=lambda item: RESOURCE_ORDER.get(item[0], 99))
        ]
        diagnostic_records = [
            {"resource_name": resource_name, "reason": reason, "count": int(count)}
            for (resource_name, reason), count in sorted(diagnostics.items())
        ]

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.86,
            tags=[{"type": "session_resource_usage", "value": "tools-skills-mcp"}],
            scores={"resource_count": float(len(counts))},
            statistics={
                "tool_count": type_distribution.get("tool", 0),
                "skill_count": type_distribution.get("skill", 0),
                "mcp_count": type_distribution.get("mcp", 0),
            },
            datasets=[
                {
                    "id": "session_resource_usage",
                    "semantic_type": "session_resource_usage",
                    "shape": "record_set",
                    "primary_key": "resource_key",
                    "records": records,
                    "schema": {
                        "resource_key": "string",
                        "resource_type": "string",
                        "resource_name": "string",
                        "count": "number",
                    },
                },
                {
                    "id": "session_resource_type_distribution",
                    "semantic_type": "frequency_distribution",
                    "shape": "record_set",
                    "primary_key": "resource_type",
                    "records": distribution_records,
                    "schema": {
                        "resource_type": "string",
                        "count": "number",
                    },
                },
                {
                    "id": "session_resource_diagnostics",
                    "semantic_type": "diagnostic_record_set",
                    "shape": "record_set",
                    "primary_key": "resource_name,reason",
                    "records": diagnostic_records,
                    "schema": {
                        "resource_name": "string",
                        "reason": "string",
                        "count": "number",
                    },
                },
            ],
            presentations=[
                {
                    "id": "session_resource_type_chart",
                    "title": "会话资源类型分布",
                    "component_ref": "builtin.bar_chart.v1",
                    "data_ref": "session_resource_type_distribution",
                    "bindings": {"x": "resource_type", "y": "count"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 72,
                },
                {
                    "id": "session_resource_usage_table",
                    "title": "会话资源使用明细",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "session_resource_usage",
                    "bindings": {"row_key": "resource_key"},
                    "routes": ["drawer"],
                    "fallback": ["builtin.json.v1"],
                    "priority": 73,
                },
            ],
            evidence_refs=evidence_refs,
        )


def _resources_for_event(event: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    resources, _ = _resources_for_event_with_diagnostics(event)
    return resources


def _resources_for_event_with_diagnostics(
    event: Mapping[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    resources: set[tuple[str, str]] = set()
    diagnostics: list[tuple[str, str]] = []

    for tool_name in _field_values(event, "tool_name", "tool", "tools"):
        if tool_name in {"function_call_output", "custom_tool_call_output"}:
            diagnostics.append((tool_name, "wrapper_tool_name"))
            continue
        resources.add(("tool", tool_name))
        mcp_server = _mcp_server_from_tool_name(tool_name)
        if mcp_server:
            resources.add(("mcp", mcp_server))

    for skill_name in _field_values(event, "skill_name", "skill", "skills"):
        if _is_valid_skill_name(skill_name, explicit=True):
            resources.add(("skill", skill_name))
        else:
            diagnostics.append((skill_name, "invalid_skill_name"))

    for mcp_server in _field_values(event, "mcp_server", "mcp_servers"):
        resources.add(("mcp", mcp_server))

    for plugin_name in _field_values(event, "plugin", "plugin_name", "plugins"):
        resources.add(("plugin", plugin_name))

    for connector_name in _field_values(event, "connector", "connector_name", "connectors"):
        resources.add(("connector", connector_name))

    text = str(event.get("text", ""))[:2000]
    for skill_name in SKILL_PATTERN.findall(text):
        if _is_valid_skill_name(skill_name, explicit=False):
            resources.add(("skill", skill_name))
        else:
            diagnostics.append((skill_name, "skill_noise"))
    for mcp_server, mcp_tool in MCP_TOOL_PATTERN.findall(text):
        resources.add(("mcp", mcp_server))
        resources.add(("tool", f"mcp__{mcp_server}__{mcp_tool}"))

    return sorted(resources), diagnostics


def _field_values(event: Mapping[str, Any], *field_names: str) -> list[str]:
    values: list[str] = []
    for field_name in field_names:
        raw_value = event.get(field_name)
        if isinstance(raw_value, str) and raw_value.strip():
            values.append(raw_value.strip())
        elif isinstance(raw_value, list):
            values.extend(str(item).strip() for item in raw_value if str(item).strip())
    return values


def _mcp_server_from_tool_name(tool_name: str) -> str:
    if not tool_name.startswith("mcp__"):
        return ""
    parts = tool_name.split("__")
    if len(parts) < 3:
        return ""
    return parts[1]


def _is_valid_skill_name(value: str, *, explicit: bool) -> bool:
    if not value or value.isdigit():
        return False
    if value in {"SkillName", "HOME", "CODEX_HOME", "PWCLI"}:
        return False
    if value.isupper() and "_" in value:
        return False
    if value.startswith("-") or value.endswith("-"):
        return False
    if ":" in value:
        left, _, right = value.partition(":")
        return bool(left and right and _is_valid_skill_name(right, explicit=explicit))
    if "-" in value:
        return bool(re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", value))
    return explicit and bool(re.fullmatch(r"[a-z][a-z0-9_]*", value))
