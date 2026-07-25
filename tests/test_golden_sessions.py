from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
REAL_GOLDEN_DIR = ROOT / "benchmarks" / "golden" / "real-sessions"
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.golden import (  # noqa: E402
    EXPECTED_GOLDEN_FACTOR_IDS,
    compare_answers,
    evaluate_golden_sessions,
    load_golden_sessions,
    score_factor_answers,
    scores_meet_threshold,
)


def test_load_golden_sessions_requires_all_factor_answers(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    payload = {
        "schema_version": "evozeus.session-golden.v1",
        "golden_id": "incomplete",
        "source_note": "test",
        "review_note": "test",
        "session": {"session_id": "s1", "events": []},
        "expected_factor_results": {"official.task-completion": {"status": "not_matched"}},
    }
    (session_dir / "01-incomplete.json").write_text(json.dumps(payload), encoding="utf-8")

    try:
        load_golden_sessions(session_dir)
    except ValueError as exc:
        assert "missing factor answers" in str(exc)
    else:
        raise AssertionError("incomplete golden session should fail validation")


def test_compare_answers_reports_nested_field_difference() -> None:
    expected = {"status": "matched", "summary": {"verdict": "completed"}}
    actual = {"status": "matched", "summary": {"verdict": "blocked"}}

    differences = compare_answers(expected, actual)

    assert differences == ["summary.verdict: expected='completed' actual='blocked'"]


def test_factor_score_uses_precision_recall_and_f1_for_labeled_events() -> None:
    expected = {
        "status": "matched",
        "events": [
            {"event_id": "u1", "kind": "dissatisfaction"},
            {"event_id": "u2", "kind": "correction_request"},
        ],
        "evidence_event_ids": ["u1", "u2"],
    }
    actual = {
        "status": "matched",
        "events": [
            {"event_id": "u1", "kind": "dissatisfaction"},
            {"event_id": "u3", "kind": "problem_report"},
        ],
        "evidence_event_ids": ["u1", "u3"],
    }

    score = score_factor_answers("official.user-input-sentiment", [(expected, actual)])

    assert score.true_positive == 1
    assert score.false_positive == 1
    assert score.false_negative == 1
    assert score.precision == 0.5
    assert score.recall == 0.5
    assert score.f1 == 0.5


def test_factor_score_counts_phrase_occurrences_without_double_scoring_evidence() -> None:
    expected = {
        "status": "matched",
        "phrases": [{"label": "不要流程图", "relation_type": "negative_constraint", "count": 2}],
        "evidence_event_ids": ["u1", "u2"],
    }
    actual = {
        "status": "matched",
        "phrases": [{"label": "不要流程图", "relation_type": "negative_constraint", "count": 1}],
        "evidence_event_ids": ["u1"],
    }

    score = score_factor_answers("official.key-sentence-trends", [(expected, actual)])

    assert score.true_positive == 1
    assert score.false_positive == 0
    assert score.false_negative == 1
    assert score.f1 == 0.6667


def test_accuracy_gate_requires_every_factor_to_reach_threshold() -> None:
    passing = score_factor_answers(
        "official.task-completion",
        [
            (
                {"status": "matched", "verdict": "completed", "verification": "verified"},
                {"status": "matched", "verdict": "completed", "verification": "verified"},
            )
        ],
    )
    failing = score_factor_answers(
        "official.task-completion",
        [
            (
                {"status": "matched", "verdict": "blocked", "verification": "blocked"},
                {"status": "matched", "verdict": "completed", "verification": "claimed"},
            )
        ],
    )

    assert scores_meet_threshold([passing], threshold=0.9)
    assert not scores_meet_threshold([passing, failing], threshold=0.9)


def test_factor_score_does_not_reward_empty_negative_sessions() -> None:
    score = score_factor_answers(
        "official.repeated-request",
        [
            (
                {"status": "matched", "chains": [{"first_event_id": "u1", "repeat_event_id": "u2"}]},
                {"status": "not_matched", "chains": []},
            ),
            (
                {"status": "not_matched", "chains": []},
                {"status": "not_matched", "chains": []},
            ),
        ],
    )

    assert score.true_positive == 0
    assert score.false_positive == 0
    assert score.false_negative == 1
    assert score.f1 == 0.0


def test_factor_score_does_not_cross_match_the_same_answer_in_another_session() -> None:
    score = score_factor_answers(
        "official.key-sentence-trends",
        [
            (
                {"status": "matched", "phrases": [{"label": "生成报告", "relation_type": "output_request", "count": 1}]},
                {"status": "not_matched", "phrases": []},
            ),
            (
                {"status": "not_matched", "phrases": []},
                {"status": "matched", "phrases": [{"label": "生成报告", "relation_type": "output_request", "count": 1}]},
            ),
        ],
    )

    assert score.true_positive == 0
    assert score.false_positive == 1
    assert score.false_negative == 1


def test_task_completion_score_includes_verification_evidence() -> None:
    score = score_factor_answers(
        "official.task-completion",
        [
            (
                {
                    "status": "matched",
                    "verdict": "completed",
                    "verification": "verified",
                    "evidence_event_ids": ["tool-result-final"],
                },
                {
                    "status": "matched",
                    "verdict": "completed",
                    "verification": "verified",
                    "evidence_event_ids": ["tool-call-earlier"],
                },
            )
        ],
    )

    assert score.true_positive == 2
    assert score.false_positive == 1
    assert score.false_negative == 1


def test_repository_golden_sessions_cover_all_official_factors() -> None:
    golden_sessions = load_golden_sessions(ROOT / "benchmarks" / "golden" / "sessions")

    assert len(golden_sessions) >= 10
    for golden in golden_sessions:
        assert set(golden.expected_factor_results) == EXPECTED_GOLDEN_FACTOR_IDS


def test_all_repository_golden_sessions_match_official_factors() -> None:
    failures = evaluate_golden_sessions(ROOT / "benchmarks" / "golden" / "sessions")

    assert failures == []


@pytest.mark.skipif(not REAL_GOLDEN_DIR.exists(), reason="local-only real Golden dataset is unavailable")
def test_real_golden_sessions_are_human_reviewed_and_source_traceable() -> None:
    real_sessions = load_golden_sessions(REAL_GOLDEN_DIR)

    assert len(real_sessions) == 5
    for golden in real_sessions:
        assert golden.review_status == "human_reviewed"
        assert golden.display_title
        assert golden.provenance["source_kind"] == "codex_jsonl_main_thread"
        assert golden.provenance["thread_source"] == "user"
        assert golden.provenance["source_fingerprint"].startswith("sha256:")
        assert golden.provenance["original_event_count"] > 300
        assert golden.provenance["retained_event_count"] > 200
