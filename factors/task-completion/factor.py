from __future__ import annotations

from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import canonical_text, classify_by_examples, event_factor_channel, safe_json_mapping


OFFICIAL_TASK_COMPLETION_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.task-completion",
    "version": "v0.1.0",
    "title": "Task completion",
    "summary": "判断一次会话里的任务是否已经完成，并给出支撑这个判断的事件证据。",
    "title_i18n": {
        "zh-CN": "任务完成判断",
        "en-US": "Task completion",
    },
    "summary_i18n": {
        "zh-CN": "判断一次会话里的任务是否已经完成，并给出支撑这个判断的事件证据。",
        "en-US": "Determines whether a task in a session has been completed and returns supporting evidence.",
    },
    "compatibility": {"evozeus_protocol": ">=0.1.0"},
    "governance": {"owner": "evozeus-factor-maintainers"},
    "input_contract": {
        "event_model": "SessionEvent[]",
        "required_fields": ["events[].id", "events[].role", "events[].text"],
        "accepted_input_kinds": ["session"],
        "target_types": ["session"],
        "record_types": ["session_envelope"],
        "prior_result_policy": "not_required",
    },
    "evidence_contract": {
        "ref_format": "event:<event-id>",
        "privacy": "Official factors must use redacted events and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["tags", "scores", "statistics", "datasets", "presentations", "verdict_signals", "evidence_refs"],
        "dataset_semantic_types": ["task_completion_verdict"],
        "presentation_components": ["builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "assistant reports task completed",
            "input": "factors/task-completion/session.json",
            "expected_status": "matched",
        }
    ],
}


class TaskCompletionFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_TASK_COMPLETION_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        signal_events: list[tuple[str, Mapping[str, Any]]] = []

        for event in context.get("events", []):
            role = str(event.get("role", ""))
            if role not in {"assistant", "tool", "system", "task_complete"}:
                continue

            if role == "task_complete":
                signal_events.append(("completed", event))
                continue
            if role == "tool" and _tool_event_failed(event):
                signal_events.append(("not_completed", event))
                continue
            if role == "assistant" and event_factor_channel(event) == "assistant_result":
                text = canonical_text(event)
                if not text:
                    continue
                verdict = _assistant_completion_verdict(text)
                if verdict in {"completed", "blocked", "not_completed"}:
                    signal_events.append((verdict, event))

        latest_signal = signal_events[-1] if signal_events else None
        if latest_signal is not None and latest_signal[0] == "completed":
            status = "matched"
            verdict = "completed"
            completion_score = 1.0
            confidence = 0.82
            evidence_events = [latest_signal[1]]
        elif latest_signal is not None and latest_signal[0] in {"not_completed", "blocked"}:
            status = "not_matched"
            verdict = latest_signal[0]
            completion_score = 0.25 if verdict == "blocked" else 0.0
            confidence = 0.74
            evidence_events = [latest_signal[1]]
        else:
            status = "not_matched"
            verdict = "unknown"
            completion_score = 0.0
            confidence = 0.45
            evidence_events = []

        records = _verdict_records(verdict, completion_score, evidence_events)
        evidence_refs = [
            {"ref_id": str(event.get("id", "")), "kind": str(event.get("role", "event"))}
            for event in evidence_events
            if event.get("id")
        ]

        return self.build_result(
            status=status,
            target_type="session",
            target_id=session_id,
            confidence=confidence,
            tags=[{"type": "task_completion", "value": verdict}],
            scores={"task_completion_score": completion_score},
            statistics={"verdict": verdict, "evidence_count": len(evidence_events)},
            datasets=[
                {
                    "id": "task_completion_verdict",
                    "semantic_type": "task_completion_verdict",
                    "shape": "record_set",
                    "primary_key": "verdict_id",
                    "records": records,
                    "schema": {
                        "verdict_id": "string",
                        "verdict": "string",
                        "completion_score": "number",
                        "evidence_event_id": "string",
                        "evidence_preview": "string",
                    },
                }
            ],
            presentations=[
                {
                    "id": "task_completion_table",
                    "title": "任务完成判断",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "task_completion_verdict",
                    "bindings": {"row_key": "verdict_id"},
                    "routes": ["dashboard", "drawer"],
                    "fallback": ["builtin.json.v1"],
                    "priority": 60,
                }
            ],
            verdict_signals=[verdict],
            evidence_refs=evidence_refs,
        )


COMPLETION_EXAMPLES = {
    "completed": [
        "已完成修改，测试通过",
        "实现完成并验证通过",
        "done, all tests pass",
        "fixed and verified",
    ],
    "blocked": [
        "我无法继续执行，因为缺少必要权限，需要你提供访问方式",
        "当前被外部依赖阻塞，需要用户补充信息",
        "blocked by missing credentials",
        "cannot proceed without access",
    ],
    "not_completed": [
        "测试仍然失败，任务还没有完成",
        "还有报错没有解决",
        "not completed, tests are failing",
        "implementation is incomplete",
    ],
    "unknown": [
        "我会继续检查",
        "正在读取代码",
        "需要进一步分析",
        "I will inspect the files",
    ],
}


def _assistant_completion_verdict(value: str) -> str:
    normalized = value.lower()
    if _contains_any(
        normalized,
        (
            "无法继续",
            "不能继续",
            "无法执行",
            "不能执行",
            "缺少必要权限",
            "需要你提供访问",
            "需要用户补充信息",
            "blocked by",
            "cannot proceed without",
            "missing credentials",
        ),
    ):
        return "blocked"
    if _contains_any(
        normalized,
        (
            "测试仍然失败",
            "仍然失败",
            "任务还没有完成",
            "还有报错没有解决",
            "not completed",
            "tests are failing",
            "implementation is incomplete",
        ),
    ):
        return "not_completed"
    if _contains_any(
        normalized,
        (
            "已完成",
            "已经完成",
            "测试通过",
            "验证通过",
            "实现完成",
            "done",
            "all tests pass",
            "tests passed",
            "fixed and verified",
        ),
    ):
        return "completed"
    classified = classify_by_examples(value, COMPLETION_EXAMPLES)
    if classified.label == "blocked":
        return "unknown"
    return classified.label if classified.score >= 0.18 else "unknown"


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term.lower() in value for term in terms)


def _tool_event_failed(event: Mapping[str, Any]) -> bool:
    tool_result = safe_json_mapping(event.get("tool_result"))
    text_result = safe_json_mapping(event.get("text"))
    if text_result:
        tool_result = {**text_result, **dict(tool_result)}
    status = str(tool_result.get("status") or tool_result.get("state") or "").lower()
    if status in {"failed", "failure", "error", "timeout", "cancelled", "canceled"}:
        return True
    if status in {"success", "succeeded", "ok", "completed", "done"}:
        return False
    for key in ("exit_code", "exitCode", "returncode", "code"):
        if key not in tool_result:
            continue
        try:
            return int(tool_result[key]) != 0
        except (TypeError, ValueError):
            continue
    stderr = str(tool_result.get("stderr") or tool_result.get("error") or "")
    if stderr.strip():
        return True
    text = str(event.get("text") or "").lower()
    return "exit code 1" in text or "exit_code" in text and "0" not in text


def _verdict_records(
    verdict: str,
    completion_score: float,
    evidence_events: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not evidence_events:
        return [
            {
                "verdict_id": "task_completion",
                "verdict": verdict,
                "completion_score": completion_score,
                "evidence_event_id": "",
                "evidence_preview": "",
            }
        ]

    return [
        {
            "verdict_id": f"task_completion_{index}",
            "verdict": verdict,
            "completion_score": completion_score,
            "evidence_event_id": str(event.get("id", "")),
            "evidence_preview": _snippet(str(event.get("text", ""))),
        }
        for index, event in enumerate(evidence_events, start=1)
    ]


def _snippet(value: str, limit: int = 120) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "..."
