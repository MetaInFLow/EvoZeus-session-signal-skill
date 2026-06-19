from __future__ import annotations

from typing import Any, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


COMPLETION_TERMS = (
    "完成",
    "已完成",
    "已经完成",
    "修复",
    "实现",
    "测试通过",
    "验证通过",
    "done",
    "completed",
    "fixed",
    "implemented",
    "tests passed",
    "all tests pass",
    "verified",
    "resolved",
)
BLOCKER_TERMS = (
    "未完成",
    "还没完成",
    "无法完成",
    "不能完成",
    "没有完成",
    "blocked",
    "not completed",
    "cannot complete",
    "unable to complete",
    "failed",
    "failing",
)


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
        completion_events: list[Mapping[str, Any]] = []
        blocker_events: list[Mapping[str, Any]] = []

        for event in context.get("events", []):
            role = str(event.get("role", ""))
            if role not in {"assistant", "tool", "system"}:
                continue

            text = str(event.get("text", ""))
            if _contains_any(text, BLOCKER_TERMS):
                blocker_events.append(event)
                continue
            if _contains_any(text, COMPLETION_TERMS):
                completion_events.append(event)

        if completion_events:
            status = "matched"
            verdict = "completed"
            completion_score = 1.0
            confidence = 0.82
            evidence_events = completion_events
        elif blocker_events:
            status = "not_matched"
            verdict = "not_completed"
            completion_score = 0.0
            confidence = 0.74
            evidence_events = blocker_events
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
                        "evidence_text": "string",
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


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    normalized = value.lower()
    return any(term.lower() in normalized for term in terms)


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
                "evidence_text": "",
            }
        ]

    return [
        {
            "verdict_id": f"task_completion_{index}",
            "verdict": verdict,
            "completion_score": completion_score,
            "evidence_event_id": str(event.get("id", "")),
            "evidence_text": _snippet(str(event.get("text", ""))),
        }
        for index, event in enumerate(evidence_events, start=1)
    ]


def _snippet(value: str, limit: int = 120) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "..."
