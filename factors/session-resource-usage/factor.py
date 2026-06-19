from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any, Iterable, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


SKILL_PATTERN = re.compile(r"(?:skill:|\$)([A-Za-z0-9_.:-]+)")
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
        "dataset_semantic_types": ["session_resource_usage", "frequency_distribution"],
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
        evidence_by_resource: dict[tuple[str, str], list[str]] = defaultdict(list)

        for event in context.get("events", []):
            event_id = str(event.get("id", ""))
            for resource_type, resource_name in _resources_for_event(event):
                key = (resource_type, resource_name)
                counts[key] += 1
                if event_id:
                    evidence_by_resource[key].append(event_id)

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
    resources: set[tuple[str, str]] = set()

    for tool_name in _field_values(event, "tool_name", "tool", "tools"):
        resources.add(("tool", tool_name))
        mcp_server = _mcp_server_from_tool_name(tool_name)
        if mcp_server:
            resources.add(("mcp", mcp_server))

    if event.get("role") == "tool" and not any(resource_type == "tool" for resource_type, _ in resources):
        resources.add(("tool", "unknown_tool"))

    for skill_name in _field_values(event, "skill_name", "skill", "skills"):
        resources.add(("skill", skill_name))

    for mcp_server in _field_values(event, "mcp_server", "mcp_servers"):
        resources.add(("mcp", mcp_server))

    for plugin_name in _field_values(event, "plugin", "plugin_name", "plugins"):
        resources.add(("plugin", plugin_name))

    for connector_name in _field_values(event, "connector", "connector_name", "connectors"):
        resources.add(("connector", connector_name))

    text = str(event.get("text", ""))
    for skill_name in SKILL_PATTERN.findall(text):
        resources.add(("skill", skill_name))

    return sorted(resources)


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
