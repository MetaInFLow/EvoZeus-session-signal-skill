from __future__ import annotations

import hashlib
from copy import deepcopy
import re
from typing import Any, Mapping

from .golden import EXPECTED_GOLDEN_FACTOR_IDS, generate_factor_answers
from .nlp import canonical_text


REAL_USER_ORIGINS = {"event_msg", "event_msg_mirror", "response_item_mirror"}
RETAINED_CHANNELS = {"user_input", "assistant_result", "tool_usage", "tool_result"}
ROLE_LIMITS = {"user": 12_000, "assistant": 8_000, "tool": 2_000, "task_complete": 1_000}

HOME_PATH_RE = re.compile(r"/Users/[^/\s]+")
TEMP_PATH_RE = re.compile(r"/var/folders/[^\s)\]}]+")
PRIVATE_FEISHU_URL_RE = re.compile(r"https?://[^\s)\]}]*(?:feishu\.cn|larksuite\.com)[^\s)\]}]*", re.I)
SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*[^\s,;]+"
)


def build_real_golden_candidate(
    envelope: Mapping[str, Any],
    *,
    golden_id: str,
    display_title: str,
    source_record_date: str = "",
) -> dict[str, Any]:
    metadata = _mapping(envelope.get("metadata"))
    thread_source = str(metadata.get("session_thread_source") or "")
    if thread_source != "user":
        raise ValueError("real Golden samples must come from a main user thread")

    raw_events = _mapping_list(envelope.get("events"))
    normalized_events: list[dict[str, Any]] = []
    redaction_count = 0
    truncated_event_count = 0
    direct_user_count = 0

    for raw_event in raw_events:
        event_metadata = _mapping(raw_event.get("metadata"))
        role = str(raw_event.get("role") or "")
        channel = str(event_metadata.get("factor_channel") or "")
        origin = str(event_metadata.get("codex_user_origin") or "")
        if channel not in RETAINED_CHANNELS or role not in ROLE_LIMITS:
            continue
        if role == "user" and origin not in REAL_USER_ORIGINS:
            continue

        event = _flatten_event(raw_event)
        event["text"] = str(raw_event.get("content") or "")
        text = canonical_text(event) if role == "user" else str(raw_event.get("content") or "")
        if role == "user":
            direct_user_count += 1
        text, event_redactions = _redact_text(text)
        redaction_count += event_redactions
        text, was_truncated = _truncate(text, ROLE_LIMITS[role])
        truncated_event_count += int(was_truncated)
        event["text"] = text
        event["raw_content_sha256"] = _sha256(str(raw_event.get("content") or ""))

        tool_result = _safe_tool_result(raw_event.get("tool_result"))
        if tool_result:
            event["tool_result"] = tool_result
        normalized_events.append(event)

    session_id = str(envelope.get("session_id") or "")
    date = source_record_date or _record_date(str(metadata.get("session_updated_at") or ""))
    session = {
        "session_id": f"real-{_sha256(session_id)[:12]}",
        "events": normalized_events,
    }
    candidate = {
        "schema_version": "evozeus.session-golden.v1",
        "golden_id": golden_id,
        "display_title": display_title,
        "source_note": "从本机 Codex 主线程 JSONL 直接抽样，保留真实事件顺序并完成脱敏",
        "review_note": "待人工逐句审阅并确认 7 个 Factor 的标准答案",
        "review_status": "needs_human_review",
        "provenance": {
            "source_kind": "codex_jsonl_main_thread",
            "source_session_id_sha256": f"sha256:{_sha256(session_id)}",
            "source_fingerprint": str(metadata.get("source_fingerprint") or ""),
            "source_record_date": date,
            "thread_source": thread_source,
            "original_event_count": len(raw_events),
            "retained_event_count": len(normalized_events),
            "direct_user_count": direct_user_count,
            "redaction_count": redaction_count,
            "truncated_event_count": truncated_event_count,
        },
        "session": session,
    }
    candidate["expected_factor_results"] = generate_factor_answers(session)
    return candidate


def apply_human_review(candidate: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    answers = _mapping(review.get("expected_factor_results"))
    if set(str(key) for key in answers) != EXPECTED_GOLDEN_FACTOR_IDS:
        raise ValueError("human review must contain all seven Factor answers")
    display_title = str(review.get("display_title") or "").strip()
    review_note = str(review.get("review_note") or "").strip()
    if not display_title or not review_note:
        raise ValueError("human review requires display_title and review_note")

    reviewed = deepcopy(dict(candidate))
    reviewed.update(
        {
            "display_title": display_title,
            "review_note": review_note,
            "review_status": "human_reviewed",
            "expected_factor_results": deepcopy(dict(answers)),
        }
    )
    return reviewed


def _flatten_event(raw_event: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _mapping(raw_event.get("metadata"))
    locator = _mapping(metadata.get("event_locator_json"))
    locator_payload = _mapping(locator.get("payload"))
    event = {
        "id": str(raw_event.get("event_id") or raw_event.get("id") or ""),
        "role": str(raw_event.get("role") or ""),
        "factor_channel": str(metadata.get("factor_channel") or ""),
        "message_scope": str(metadata.get("message_scope") or ""),
        "codex_user_origin": str(metadata.get("codex_user_origin") or ""),
        "codex_record_type": str(metadata.get("codex_record_type") or ""),
        "codex_event_type": str(metadata.get("codex_event_type") or ""),
        "source_line": int(locator_payload.get("line_start") or 0),
    }
    tool_name = str(raw_event.get("tool_name") or "")
    if tool_name:
        event["tool_name"] = tool_name
    return event


def _redact_text(text: str) -> tuple[str, int]:
    redacted = text
    count = 0
    for pattern, replacement in (
        (PRIVATE_FEISHU_URL_RE, "[private-feishu-url]"),
        (TEMP_PATH_RE, "[local-attachment-path]"),
        (HOME_PATH_RE, "$HOME"),
        (SECRET_RE, "[redacted-secret]"),
    ):
        redacted, replacements = pattern.subn(replacement, redacted)
        count += replacements
    return redacted, count


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "\n\n[内容过长，已在脱敏样本中截断]", True


def _safe_tool_result(value: Any) -> dict[str, Any]:
    raw = _mapping(value)
    safe = {}
    for key in ("call_id", "status", "state", "exit_code", "exitCode", "returncode", "code"):
        if key in raw and isinstance(raw[key], (str, int, float, bool, type(None))):
            safe[key] = raw[key]
    return safe


def _record_date(value: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else ""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
