from __future__ import annotations

import re
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import canonical_text, event_factor_channel, is_direct_user_input, safe_json_mapping


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
        selected_signal: tuple[str, str, Mapping[str, Any]] | None = None
        selected_verification_priority = 0
        call_text_by_id: dict[str, str] = {}

        for event in context.get("events", []):
            role = str(event.get("role", ""))
            if role == "tool" and event_factor_channel(event) == "tool_usage":
                call_id = _tool_call_id(event)
                if call_id:
                    call_text_by_id[call_id] = str(event.get("text") or "")

            if is_direct_user_input(event):
                selected_signal = None
                selected_verification_priority = 0
                call_text_by_id.clear()
                text = canonical_text(event)
                if _contains_any(text.lower(), USER_REJECTION_TERMS):
                    selected_signal = ("not_completed", "user_rejected", event)
                continue

            if role not in {"assistant", "tool", "system", "task_complete"}:
                continue

            if role == "task_complete":
                if selected_signal is None or selected_signal[1] == "claimed":
                    selected_signal = ("completed", "runtime_closed", event)
                continue
            if role == "tool" and _tool_event_failed(event):
                selected_signal = ("not_completed", "tool_failed", event)
                selected_verification_priority = 0
                continue
            verification_priority = _verification_tool_priority(event, call_text_by_id) if role == "tool" else 0
            if verification_priority:
                if (
                    selected_signal is None
                    or selected_signal[1] != "verified"
                    or verification_priority > selected_verification_priority
                ):
                    selected_signal = ("completed", "verified", event)
                    selected_verification_priority = verification_priority
                continue
            if role == "assistant" and event_factor_channel(event) == "assistant_result":
                text = canonical_text(event)
                if not text:
                    continue
                verdict = _assistant_completion_verdict(text)
                if verdict in {"completed", "blocked", "not_completed"}:
                    verification = "claimed" if verdict == "completed" else verdict
                    if selected_signal is None or selected_signal[1] != "verified" or verdict != "completed":
                        selected_signal = (verdict, verification, event)

        if selected_signal is not None and selected_signal[0] == "completed":
            status = "matched"
            verdict = "completed"
            verification = selected_signal[1]
            completion_score = 1.0
            confidence = 0.82
            evidence_events = [selected_signal[2]]
        elif selected_signal is not None and selected_signal[0] in {"not_completed", "blocked"}:
            status = "not_matched"
            verdict = selected_signal[0]
            verification = selected_signal[1]
            completion_score = 0.25 if verdict == "blocked" else 0.0
            confidence = 0.74
            evidence_events = [selected_signal[2]]
        else:
            status = "not_matched"
            verdict = "unknown"
            verification = "none"
            completion_score = 0.0
            confidence = 0.45
            evidence_events = []

        records = _verdict_records(verdict, verification, completion_score, evidence_events)
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
            statistics={"verdict": verdict, "verification": verification, "evidence_count": len(evidence_events)},
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
                        "verification": "string",
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
            "还差几个关键信息",
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
            "我会继续",
            "我会先",
            "接下来",
            "现在开始",
            "正在",
            "需要进一步",
            "i will",
            "next i",
        ),
    ):
        return "unknown"
    if _contains_any(
        normalized,
        (
            "已完成",
            "已经完成",
            "测试通过",
            "验证通过",
            "实现完成",
            "修复了",
            "已修复",
            "更新了",
            "已更新",
            "新增",
            "已新增",
            "添加了",
            "已添加",
            "guide created",
            "added ",
            "updated ",
            "removed ",
            "fixed ",
            "implemented ",
            "done",
            "all tests pass",
            "tests passed",
            "fixed and verified",
        ),
    ):
        return "completed"
    return "unknown"


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


def _verification_tool_succeeded(event: Mapping[str, Any], call_text_by_id: Mapping[str, str]) -> bool:
    return _verification_tool_priority(event, call_text_by_id) > 0


def _verification_tool_priority(event: Mapping[str, Any], call_text_by_id: Mapping[str, str]) -> int:
    if event_factor_channel(event) != "tool_result":
        return 0
    if not _tool_event_succeeded(event):
        return 0
    call_text = call_text_by_id.get(_tool_call_id(event), "")
    combined = f"{call_text}\n{event.get('text', '')}".lower()
    if VERIFICATION_FAILURE_OUTPUT_RE.search(str(event.get("text") or "")):
        return 0
    if RELEASE_VERIFICATION_RE.search(combined) and "|| true" not in call_text:
        return 4
    if POSITIVE_CONTENT_CHECK_RE.search(combined):
        return 3
    if VERIFICATION_COMMAND_RE.search(combined) or VERIFICATION_OUTPUT_RE.search(combined):
        return 2
    return 0


def _tool_event_succeeded(event: Mapping[str, Any]) -> bool:
    tool_result = safe_json_mapping(event.get("tool_result"))
    text_result = safe_json_mapping(event.get("text"))
    if text_result:
        tool_result = {**text_result, **dict(tool_result)}
    status = str(tool_result.get("status") or tool_result.get("state") or "").lower()
    if status in {"success", "succeeded", "ok", "completed", "done"}:
        return True
    for key in ("exit_code", "exitCode", "returncode", "code"):
        if key not in tool_result:
            continue
        try:
            return int(tool_result[key]) == 0
        except (TypeError, ValueError):
            continue
    return bool(re.search(r"process exited with code\s*0", str(event.get("text") or ""), re.I))


def _tool_call_id(event: Mapping[str, Any]) -> str:
    tool_result = safe_json_mapping(event.get("tool_result"))
    return str(tool_result.get("call_id") or event.get("call_id") or "")


def _verdict_records(
    verdict: str,
    verification: str,
    completion_score: float,
    evidence_events: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not evidence_events:
        return [
            {
                "verdict_id": "task_completion",
                "verdict": verdict,
                "verification": verification,
                "completion_score": completion_score,
                "evidence_event_id": "",
                "evidence_preview": "",
            }
        ]

    return [
        {
            "verdict_id": f"task_completion_{index}",
            "verdict": verdict,
            "verification": verification,
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


USER_REJECTION_TERMS = (
    "不对",
    "不是我想要",
    "没有解决",
    "还是不行",
    "仍然不行",
    "改动太大",
)
VERIFICATION_COMMAND_RE = re.compile(
    r"\b(?:pytest|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|cargo\s+test|go\s+test)\b"
    r"|\bgit\s+diff\s+--check\b"
    r"|\b(?:npm|pnpm|yarn|cargo|go)\s+(?:run\s+)?(?:build|check|verify)\b",
    re.I,
)
RELEASE_VERIFICATION_RE = re.compile(r"\bgh\s+release\s+view\b", re.I)
POSITIVE_CONTENT_CHECK_RE = re.compile(r"\brg\s+-n\s+[^\n]{0,240}https?://", re.I)
VERIFICATION_OUTPUT_RE = re.compile(r"\b\d+\s+passed\b|tests? passed|验证通过|测试通过", re.I)
VERIFICATION_FAILURE_OUTPUT_RE = re.compile(
    r"unknown json field"
    r"|\btraceback\b"
    r"|\b(?:error|errors):"
    r"|\b[1-9]\d*\s+(?:tests?\s+)?failed\b"
    r"|\bfail\s+[1-9]\d*\b",
    re.I,
)
