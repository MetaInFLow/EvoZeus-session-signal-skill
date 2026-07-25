from __future__ import annotations

import base64
from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .golden import GoldenSession, load_golden_sessions


FACTOR_ORDER = (
    "official.task-completion",
    "official.user-input-sentiment",
    "official.repeated-request",
    "official.tool-failure-frequency",
    "official.session-resource-usage",
    "official.key-sentence-trends",
    "official.semantic-phrase-clusters",
)

FACTOR_NAMES = {
    "official.task-completion": "任务完成情况",
    "official.user-input-sentiment": "用户反馈",
    "official.repeated-request": "重复请求",
    "official.tool-failure-frequency": "工具失败与恢复",
    "official.session-resource-usage": "使用了哪些能力",
    "official.key-sentence-trends": "关键表达",
    "official.semantic-phrase-clusters": "相似表达聚类",
}

SESSION_TITLES = {
    "01-verified-completion": "已修复，并通过测试验证",
    "02-final-blocker": "因缺少权限而受阻",
    "03-explicit-correction": "用户明确否定当前结果",
    "04-semantic-repeated-request": "同一需求被再次提出",
    "05-pasted-log-not-request": "补充日志不是重复请求",
    "06-tool-failure-and-recovery": "工具失败后成功恢复",
    "07-resource-usage": "明确使用 Skill 和 MCP",
    "08-key-sentence-constraints": "一句话里的顺序与边界",
    "09-run-project-phrases": "“启动项目”的多种说法",
    "10-pasted-prompt-noise": "粘贴 Prompt 不代表使用习惯",
}

ROLE_NAMES = {
    "user": "用户",
    "assistant": "AI",
    "tool": "工具",
    "task_complete": "系统",
}

RELATION_NAMES = {
    "action_request": "操作请求",
    "negative_constraint": "禁止约束",
    "sequence_step": "执行顺序",
    "output_request": "输出要求",
}

SENTIMENT_NAMES = {
    "correction_request": "纠正请求",
    "problem_report": "问题反馈",
    "dissatisfaction": "不满意",
    "positive_feedback": "正向反馈",
}


def build_report_data(sessions: Iterable[GoldenSession]) -> dict[str, Any]:
    session_views = [_build_session_view(session) for session in sessions]
    return {
        "title": "Golden Session 人工标注审阅台",
        "session_count": len(session_views),
        "factor_count": len(FACTOR_ORDER),
        "annotation_count": sum(
            len(event["labels"])
            for session in session_views
            for event in session["events"]
        ),
        "sessions": session_views,
    }


def render_report(
    *,
    golden_dir: Path,
    template_path: Path,
    output_path: Path,
    logo_path: Path,
) -> Path:
    report_data = build_report_data(load_golden_sessions(golden_dir))
    data_json = json.dumps(report_data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    logo_data_uri = _image_data_uri(logo_path)
    template = template_path.read_text(encoding="utf-8")
    if "__GOLDEN_REPORT_DATA__" not in template or "__ZEUS_LOGO_DATA_URI__" not in template:
        raise ValueError("golden report template is missing required placeholders")
    html = template.replace("__GOLDEN_REPORT_DATA__", data_json).replace(
        "__ZEUS_LOGO_DATA_URI__", logo_data_uri
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _build_session_view(golden: GoldenSession) -> dict[str, Any]:
    events = [dict(event) for event in golden.session.get("events", []) if isinstance(event, Mapping)]
    labels_by_event: dict[str, list[dict[str, str]]] = {
        str(event.get("id") or ""): [] for event in events
    }
    expected = golden.expected_factor_results

    _attach_task_completion(labels_by_event, expected["official.task-completion"])
    _attach_user_feedback(labels_by_event, expected["official.user-input-sentiment"])
    _attach_repeated_requests(labels_by_event, expected["official.repeated-request"])
    _attach_tool_failures(labels_by_event, expected["official.tool-failure-frequency"])
    _attach_resource_usage(labels_by_event, events, expected["official.session-resource-usage"])
    _attach_key_sentences(labels_by_event, events, expected["official.key-sentence-trends"])
    _attach_semantic_clusters(labels_by_event, events, expected["official.semantic-phrase-clusters"])

    event_views = []
    for event in events:
        event_id = str(event.get("id") or "")
        role = str(event.get("role") or "unknown")
        labels = _deduplicate_labels(labels_by_event.get(event_id, []))
        event_views.append(
            {
                "event_id": event_id,
                "role": role,
                "role_name": ROLE_NAMES.get(role, "系统"),
                "text": str(event.get("text") or ""),
                "source_line": int(event.get("source_line") or 0),
                "codex_user_origin": str(event.get("codex_user_origin") or ""),
                "labels": labels,
                "empty_label": "" if labels else _empty_label(role),
            }
        )

    return {
        "golden_id": golden.golden_id,
        "session_id": str(golden.session.get("session_id") or ""),
        "title": golden.display_title or SESSION_TITLES.get(golden.golden_id, golden.review_note or golden.golden_id),
        "source_note": golden.source_note,
        "review_note": golden.review_note,
        "review_status": golden.review_status,
        "provenance": dict(golden.provenance),
        "is_real_codex_session": golden.provenance.get("source_kind") == "codex_jsonl_main_thread",
        "events": event_views,
        "factors": [
            _factor_summary(factor_id, expected[factor_id]) for factor_id in FACTOR_ORDER
        ],
        "annotation_count": sum(len(event["labels"]) for event in event_views),
    }


def _attach_task_completion(
    labels_by_event: dict[str, list[dict[str, str]]], result: Mapping[str, Any]
) -> None:
    verdict = str(result.get("verdict") or "unknown")
    verification = str(result.get("verification") or "none")
    values = {
        "completed": ("任务已完成", "green"),
        "blocked": ("任务受阻", "orange"),
        "not_completed": ("任务未完成", "red"),
    }
    if verdict not in values:
        return
    value, tone = values[verdict]
    detail = {
        "verified": "有成功的测试或工具结果作为验证",
        "claimed": "只有完成声明，没有独立验证",
        "blocked": "缺少外部条件，当前无法继续",
        "user_rejected": "用户明确否定了当前结果",
    }.get(verification, "人工判断的最终任务状态")
    for event_id in _string_list(result.get("evidence_event_ids")):
        _add_label(labels_by_event, event_id, "任务完成情况", value, detail, tone)


def _attach_user_feedback(
    labels_by_event: dict[str, list[dict[str, str]]], result: Mapping[str, Any]
) -> None:
    for record in _mapping_list(result.get("events")):
        event_id = str(record.get("event_id") or "")
        kind = str(record.get("kind") or "")
        value = SENTIMENT_NAMES.get(kind, kind or "用户反馈")
        tone = "red" if kind in {"correction_request", "dissatisfaction"} else "orange"
        _add_label(
            labels_by_event,
            event_id,
            "用户反馈",
            value,
            f"用户在这句话中直接表达了{value}",
            tone,
        )


def _attach_repeated_requests(
    labels_by_event: dict[str, list[dict[str, str]]], result: Mapping[str, Any]
) -> None:
    for chain in _mapping_list(result.get("chains")):
        first_id = str(chain.get("first_event_id") or "")
        repeat_id = str(chain.get("repeat_event_id") or "")
        _add_label(
            labels_by_event,
            first_id,
            "重复请求",
            "首次提出",
            "这项需求之后被用户换一种说法再次提出",
            "blue",
        )
        _add_label(
            labels_by_event,
            repeat_id,
            "重复请求",
            "重复提出",
            "与前一次请求表达的是同一个未解决意图",
            "red",
        )


def _attach_tool_failures(
    labels_by_event: dict[str, list[dict[str, str]]], result: Mapping[str, Any]
) -> None:
    tools = _mapping_list(result.get("tools"))
    if not tools:
        return
    details = []
    for tool in tools:
        tool_name = str(tool.get("tool_name") or "未知工具")
        failure_count = int(tool.get("failure_count") or 0)
        recovered_count = int(tool.get("recovered_count") or 0)
        unrecovered_count = int(tool.get("unrecovered_count") or 0)
        recovery = f"，其中 {recovered_count} 次后来恢复" if recovered_count else ""
        unresolved = f"，仍有 {unrecovered_count} 次未恢复" if unrecovered_count else ""
        details.append(f"{tool_name} 失败 {failure_count} 次{recovery}{unresolved}")
    detail = "；".join(details)
    tone = "red" if any(int(tool.get("unrecovered_count") or 0) for tool in tools) else "orange"
    for event_id in _string_list(result.get("evidence_event_ids")):
        _add_label(labels_by_event, event_id, "工具失败与恢复", "发生工具失败", detail, tone)


def _attach_resource_usage(
    labels_by_event: dict[str, list[dict[str, str]]],
    events: list[dict[str, Any]],
    result: Mapping[str, Any],
) -> None:
    resources = _mapping_list(result.get("resources"))
    event_by_id = {str(event.get("id") or ""): event for event in events}
    for event_id in _string_list(result.get("evidence_event_ids")):
        event = event_by_id.get(event_id, {})
        skill_name = str(event.get("skill_name") or "")
        tool_name = str(event.get("tool_name") or "")
        matched_resources = [
            resource
            for resource in resources
            if _resource_matches_event(resource, skill_name=skill_name, tool_name=tool_name)
        ]
        if not matched_resources and len(result.get("evidence_event_ids") or []) == 1:
            matched_resources = resources
        for resource in matched_resources:
            resource_type = str(resource.get("resource_type") or "resource")
            resource_name = str(resource.get("resource_name") or "未知能力")
            type_name = {"skill": "Skill", "mcp": "MCP", "tool": "工具"}.get(
                resource_type, "能力"
            )
            count = int(resource.get("count") or 0)
            _add_label(
                labels_by_event,
                event_id,
                "使用了哪些能力",
                f"{type_name} · {resource_name}",
                f"这条记录证明该能力在本 Session 中实际使用了 {count} 次",
                "green",
            )


def _attach_key_sentences(
    labels_by_event: dict[str, list[dict[str, str]]],
    events: list[dict[str, Any]],
    result: Mapping[str, Any],
) -> None:
    evidence_ids = set(_string_list(result.get("evidence_event_ids")))
    for phrase in _mapping_list(result.get("phrases")):
        label = str(phrase.get("label") or "")
        relation_type = str(phrase.get("relation_type") or "")
        value = RELATION_NAMES.get(relation_type, relation_type or "关键表达")
        matching_ids = [
            str(event.get("id") or "")
            for event in events
            if str(event.get("id") or "") in evidence_ids and label and label in str(event.get("text") or "")
        ]
        if not matching_ids and len(evidence_ids) == 1:
            matching_ids = list(evidence_ids)
        for event_id in matching_ids:
            _add_label(
                labels_by_event,
                event_id,
                "关键表达",
                value,
                f"人工摘出的原句：“{label}”",
                "gold",
            )


def _attach_semantic_clusters(
    labels_by_event: dict[str, list[dict[str, str]]],
    events: list[dict[str, Any]],
    result: Mapping[str, Any],
) -> None:
    evidence_ids = set(_string_list(result.get("evidence_event_ids")))
    for cluster in _mapping_list(result.get("clusters")):
        cluster_label = str(cluster.get("label") or "相似表达")
        variants = _string_list(cluster.get("variants"))
        for event in events:
            event_id = str(event.get("id") or "")
            text = str(event.get("text") or "")
            if event_id not in evidence_ids or not any(variant in text for variant in variants):
                continue
            matched_variant = next(variant for variant in variants if variant in text)
            _add_label(
                labels_by_event,
                event_id,
                "相似表达聚类",
                cluster_label,
                f"“{matched_variant}”与本组其他说法表达同一意图",
                "purple",
            )


def _factor_summary(factor_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    if factor_id == "official.task-completion":
        verdict = str(result.get("verdict") or "unknown")
        verification = str(result.get("verification") or "none")
        completed_summary = {
            "verified": "已完成，并有独立验证",
            "runtime_closed": "运行已经结束，但没有独立验证",
            "claimed": "AI 声明已完成，但没有独立验证",
        }.get(verification, "已完成，验证情况不明确")
        summary = {
            "completed": completed_summary,
            "blocked": "任务受阻，等待外部条件",
            "not_completed": "任务未完成，用户否定结果" if verification == "user_rejected" else "任务未完成",
            "unknown": "当前记录不足以判断是否完成",
        }.get(verdict, "当前记录不足以判断")
        active = verdict != "unknown"
        details = []
        tone = {"completed": "green", "blocked": "orange", "not_completed": "red"}.get(verdict, "muted")
    elif factor_id == "official.user-input-sentiment":
        records = _mapping_list(result.get("events"))
        active = bool(records)
        details = [SENTIMENT_NAMES.get(str(record.get("kind") or ""), str(record.get("kind") or "")) for record in records]
        sentiment_counts = Counter(details)
        summary_parts = [
            f"{sentiment_counts[name]} 次{name}"
            for name in ("纠正请求", "不满意", "问题反馈", "正向反馈")
            if sentiment_counts.get(name)
        ]
        summary = "，".join(summary_parts) if summary_parts else "没有明显的负向反馈或纠正"
        tone = "red" if active else "muted"
    elif factor_id == "official.repeated-request":
        chains = _mapping_list(result.get("chains"))
        active = bool(chains)
        details = [f"{chain.get('first_event_id')} → {chain.get('repeat_event_id')}" for chain in chains]
        summary = f"发现 {len(chains)} 次语义重复" if chains else "没有重复提出同一需求"
        tone = "red" if active else "muted"
    elif factor_id == "official.tool-failure-frequency":
        tools = _mapping_list(result.get("tools"))
        active = bool(tools)
        details = [
            f"{tool.get('tool_name')}：失败 {tool.get('failure_count', 0)} 次，恢复 {tool.get('recovered_count', 0)} 次"
            for tool in tools
        ]
        summary = "；".join(details) if details else "没有记录到工具失败"
        tone = "orange" if active else "muted"
    elif factor_id == "official.session-resource-usage":
        resources = _mapping_list(result.get("resources"))
        active = bool(resources)
        details = [
            f"{_resource_type_name(resource.get('resource_type'))} · {resource.get('resource_name')} × {resource.get('count', 0)}"
            for resource in resources
        ]
        call_count = sum(int(resource.get("count") or 0) for resource in resources)
        summary = (
            f"实际使用 {len(resources)} 种能力，共 {call_count} 次调用"
            if details
            else "没有明确记录 Skill、MCP 或工具使用"
        )
        tone = "green" if active else "muted"
    elif factor_id == "official.key-sentence-trends":
        phrases = _mapping_list(result.get("phrases"))
        active = bool(phrases)
        details = [
            f"{RELATION_NAMES.get(str(phrase.get('relation_type') or ''), '关键表达')}：“{phrase.get('label')}”"
            for phrase in phrases
        ]
        summary = f"人工摘出 {len(phrases)} 条关键表达" if phrases else "没有摘出关键表达"
        tone = "gold" if active else "muted"
    else:
        clusters = _mapping_list(result.get("clusters"))
        active = bool(clusters)
        details = [
            f"{cluster.get('label')}：{' / '.join(_string_list(cluster.get('variants')))}"
            for cluster in clusters
        ]
        summary = f"形成 {len(clusters)} 个相似表达组" if clusters else "没有形成相似表达组"
        tone = "purple" if active else "muted"

    return {
        "key": factor_id.removeprefix("official."),
        "name": FACTOR_NAMES[factor_id],
        "summary": summary,
        "details": details,
        "active": active,
        "tone": tone,
        "evidence_count": len(set(_string_list(result.get("evidence_event_ids")))),
    }


def _add_label(
    labels_by_event: dict[str, list[dict[str, str]]],
    event_id: str,
    factor: str,
    value: str,
    detail: str,
    tone: str,
) -> None:
    if event_id not in labels_by_event:
        return
    labels_by_event[event_id].append(
        {"factor": factor, "value": value, "detail": detail, "tone": tone}
    )


def _deduplicate_labels(labels: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for label in labels:
        key = (label["factor"], label["value"], label["detail"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(label)
    return unique


def _resource_matches_event(
    resource: Mapping[str, Any], *, skill_name: str, tool_name: str
) -> bool:
    resource_type = str(resource.get("resource_type") or "")
    resource_name = str(resource.get("resource_name") or "")
    if resource_type == "skill":
        return bool(skill_name and skill_name == resource_name)
    if resource_type == "tool":
        return bool(tool_name and tool_name == resource_name)
    if resource_type == "mcp":
        return bool(tool_name and (f"mcp__{resource_name}__" in tool_name or resource_name in tool_name))
    return False


def _empty_label(role: str) -> str:
    return {
        "assistant": "AI 回复，仅作为会话上下文",
        "tool": "这条工具记录没有被人工答案选为证据",
        "task_complete": "系统结束标记，不参与用户画像",
        "user": "这句话没有命中当前 7 个 Factor",
    }.get(role, "这条记录没有人工标签")


def _resource_type_name(value: Any) -> str:
    return {"tool": "工具", "skill": "Skill", "mcp": "MCP"}.get(str(value or ""), "能力")


def _image_data_uri(path: Path) -> str:
    mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
