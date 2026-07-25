from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.real_golden import (  # noqa: E402
    apply_human_review,
    build_real_golden_candidate,
)


def _event(
    event_id: str,
    role: str,
    content: str,
    *,
    channel: str,
    scope: str = "",
    origin: str = "",
    line: int,
    tool_name: str | None = None,
    tool_result: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "role": role,
        "content": content,
        "tool_name": tool_name,
        "tool_result": tool_result,
        "metadata": {
            "factor_channel": channel,
            "message_scope": scope,
            "codex_user_origin": origin,
            "codex_record_type": "response_item",
            "codex_event_type": "message" if role in {"user", "assistant"} else "function_call_output",
            "event_locator_json": {
                "payload": {"line_start": line, "line_end": line, "source_path": "/Users/test/.codex/raw.jsonl"}
            },
        },
    }


def _main_thread_envelope() -> dict[str, object]:
    return {
        "session_id": "source-session-123",
        "provider": "codex",
        "source_ref": "/Users/test/.codex/sessions/raw.jsonl",
        "metadata": {
            "source_fingerprint": "sha256:source-fingerprint",
            "session_title": "真实长会话",
            "session_updated_at": "2026-07-11T08:00:00Z",
            "session_thread_source": "user",
            "session_source_kind": "vscode",
        },
        "events": [
            _event(
                "context-1",
                "user",
                "# AGENTS.md instructions\nnot real user text",
                channel="context",
                scope="context_wrapper",
                origin="synthetic_context",
                line=2,
            ),
            _event(
                "user-1",
                "user",
                "<in-app-browser-context>noise</in-app-browser-context>\n## My request for Codex:\n不对，改动太大了，不要删除数据库",
                channel="user_input",
                scope="context_wrapper",
                origin="event_msg_mirror",
                line=7,
            ),
            _event(
                "assistant-1",
                "assistant",
                "我会重新检查。",
                channel="assistant_result",
                line=10,
            ),
            _event(
                "reasoning-1",
                "reasoning",
                "private chain of thought",
                channel="context",
                line=11,
            ),
            _event(
                "tool-1",
                "tool",
                "cat /Users/test/private/file.md https://metainflow.feishu.cn/private",
                channel="tool_usage",
                line=12,
                tool_name="exec_command",
            ),
            _event(
                "tool-output-1",
                "tool",
                "password=top-secret\nProcess exited with code 0",
                channel="tool_result",
                line=13,
                tool_name="function_call_output",
                tool_result={"exit_code": 0, "status": "success", "call_id": "call-1"},
            ),
            _event(
                "complete-1",
                "task_complete",
                "Task complete",
                channel="assistant_result",
                line=14,
            ),
        ],
    }


def test_real_golden_candidate_requires_a_structural_main_thread_marker() -> None:
    envelope = _main_thread_envelope()
    envelope["metadata"]["session_thread_source"] = "subagent"

    try:
        build_real_golden_candidate(envelope, golden_id="real-01", display_title="真实样本")
    except ValueError as exc:
        assert "main user thread" in str(exc)
    else:
        raise AssertionError("subagent session must not become a real Golden sample")


def test_real_golden_candidate_keeps_real_conversation_and_provenance() -> None:
    candidate = build_real_golden_candidate(
        _main_thread_envelope(),
        golden_id="real-01",
        display_title="用户纠正真实样本",
    )

    assert candidate["review_status"] == "needs_human_review"
    assert candidate["provenance"] == {
        "source_kind": "codex_jsonl_main_thread",
        "source_session_id_sha256": candidate["provenance"]["source_session_id_sha256"],
        "source_fingerprint": "sha256:source-fingerprint",
        "source_record_date": "2026-07-11",
        "thread_source": "user",
        "original_event_count": 7,
        "retained_event_count": 5,
        "direct_user_count": 1,
        "redaction_count": 3,
        "truncated_event_count": 0,
    }
    events = candidate["session"]["events"]
    assert [event["id"] for event in events] == [
        "user-1",
        "assistant-1",
        "tool-1",
        "tool-output-1",
        "complete-1",
    ]
    assert events[0]["text"] == "不对，改动太大了，不要删除数据库"
    assert events[0]["source_line"] == 7
    assert events[0]["codex_user_origin"] == "event_msg_mirror"
    serialized = str(candidate)
    assert "/Users/test" not in serialized
    assert "metainflow.feishu.cn" not in serialized
    assert "top-secret" not in serialized
    assert "private chain of thought" not in serialized


def test_real_golden_candidate_contains_answers_for_all_seven_factors() -> None:
    candidate = build_real_golden_candidate(
        _main_thread_envelope(),
        golden_id="real-01",
        display_title="用户纠正真实样本",
    )

    assert set(candidate["expected_factor_results"]) == {
        "official.task-completion",
        "official.user-input-sentiment",
        "official.repeated-request",
        "official.tool-failure-frequency",
        "official.session-resource-usage",
        "official.key-sentence-trends",
        "official.semantic-phrase-clusters",
    }


def test_human_review_replaces_seed_answers_and_marks_sample_reviewed() -> None:
    candidate = build_real_golden_candidate(
        _main_thread_envelope(),
        golden_id="real-01",
        display_title="候选标题",
    )
    reviewed_answers = dict(candidate["expected_factor_results"])
    reviewed_answers["official.task-completion"] = {
        "status": "not_matched",
        "verdict": "not_completed",
        "verification": "user_rejected",
        "evidence_event_ids": ["user-1"],
    }

    reviewed = apply_human_review(
        candidate,
        {
            "display_title": "人工审阅标题",
            "review_note": "逐条查看聊天和工具证据后确认",
            "expected_factor_results": reviewed_answers,
        },
    )

    assert reviewed["review_status"] == "human_reviewed"
    assert reviewed["display_title"] == "人工审阅标题"
    assert reviewed["review_note"] == "逐条查看聊天和工具证据后确认"
    assert reviewed["expected_factor_results"]["official.task-completion"]["verification"] == "user_rejected"


def test_human_review_rejects_missing_factor_answer() -> None:
    candidate = build_real_golden_candidate(
        _main_thread_envelope(),
        golden_id="real-01",
        display_title="候选标题",
    )

    try:
        apply_human_review(
            candidate,
            {
                "display_title": "标题",
                "review_note": "说明",
                "expected_factor_results": {"official.task-completion": {}},
            },
        )
    except ValueError as exc:
        assert "all seven Factor answers" in str(exc)
    else:
        raise AssertionError("incomplete human review must be rejected")
