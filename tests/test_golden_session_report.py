from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
REAL_GOLDEN_DIR = ROOT / "benchmarks" / "golden" / "real-sessions"
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.golden import load_golden_sessions  # noqa: E402
from evozeus_session_signal_skill.golden_report import (  # noqa: E402
    build_report_data,
    render_report,
)


def _report_data() -> dict[str, object]:
    sessions = load_golden_sessions(ROOT / "benchmarks" / "golden" / "sessions")
    return build_report_data(sessions)


def test_report_data_contains_all_golden_sessions_and_chinese_factor_names() -> None:
    report = _report_data()

    assert report["session_count"] == 10
    assert report["factor_count"] == 7
    first_session = report["sessions"][0]
    assert [factor["name"] for factor in first_session["factors"]] == [
        "任务完成情况",
        "用户反馈",
        "重复请求",
        "工具失败与恢复",
        "使用了哪些能力",
        "关键表达",
        "相似表达聚类",
    ]
    resource_factor = next(
        factor for factor in first_session["factors"] if factor["name"] == "使用了哪些能力"
    )
    assert resource_factor["summary"] == "实际使用 1 种能力，共 1 次调用"


def test_report_data_attaches_human_labels_to_the_exact_chat_message() -> None:
    report = _report_data()
    correction_session = next(
        session for session in report["sessions"] if session["golden_id"] == "03-explicit-correction"
    )
    correction_event = next(
        event for event in correction_session["events"] if event["event_id"] == "user-correction"
    )

    labels = {(label["factor"], label["value"]) for label in correction_event["labels"]}
    assert ("任务完成情况", "任务未完成") in labels
    assert ("用户反馈", "纠正请求") in labels
    assert ("关键表达", "禁止约束") in labels

    assistant_event = next(
        event for event in correction_session["events"] if event["event_id"] == "assistant-claimed"
    )
    assert assistant_event["labels"] == []
    assert assistant_event["empty_label"] == "AI 回复，仅作为会话上下文"


def test_report_data_marks_semantic_rephrases_on_each_matching_turn() -> None:
    report = _report_data()
    run_session = next(
        session for session in report["sessions"] if session["golden_id"] == "09-run-project-phrases"
    )

    clustered_event_ids = {
        event["event_id"]
        for event in run_session["events"]
        if any(label["factor"] == "相似表达聚类" for label in event["labels"])
    }
    assert clustered_event_ids == {"user-run-1", "user-run-2", "user-run-3", "user-run-4"}
    report_event = next(event for event in run_session["events"] if event["event_id"] == "user-report")
    assert not any(label["factor"] == "相似表达聚类" for label in report_event["labels"])


def test_render_report_embeds_data_and_removes_template_placeholder(tmp_path: Path) -> None:
    output_path = tmp_path / "index.html"

    render_report(
        golden_dir=ROOT / "benchmarks" / "golden" / "sessions",
        template_path=ROOT / "templates" / "golden-session-review" / "index.html",
        output_path=output_path,
        logo_path=ROOT / "templates" / "ai-usage-profile-report" / "assets" / "evozeus-gold-512.png",
    )

    html = output_path.read_text(encoding="utf-8")
    assert "__GOLDEN_REPORT_DATA__" not in html
    assert "__ZEUS_LOGO_DATA_URI__" not in html
    assert "Golden Session 人工标注审阅台" in html
    assert '"golden_id":"03-explicit-correction"' in html
    assert "不对，改动太大了，排版不要大变化" in html


@pytest.mark.skipif(not REAL_GOLDEN_DIR.exists(), reason="local-only real Golden dataset is unavailable")
def test_report_data_exposes_real_session_provenance_and_full_conversation() -> None:
    sessions = load_golden_sessions(REAL_GOLDEN_DIR)

    report = build_report_data(sessions)

    assert report["session_count"] == 5
    first = report["sessions"][0]
    assert first["title"] == "官网定位反复纠偏与用户价值重构"
    assert first["is_real_codex_session"] is True
    assert first["provenance"]["original_event_count"] == 871
    assert first["provenance"]["retained_event_count"] == 264
    assert first["provenance"]["direct_user_count"] == 25
    assert len(first["events"]) == 264
    task_factor = next(factor for factor in first["factors"] if factor["name"] == "任务完成情况")
    sentiment_factor = next(factor for factor in first["factors"] if factor["name"] == "用户反馈")
    resource_factor = next(factor for factor in first["factors"] if factor["name"] == "使用了哪些能力")
    assert task_factor["summary"] == "运行已经结束，但没有独立验证"
    assert sentiment_factor["summary"] == "8 次纠正请求，4 次不满意"
    assert resource_factor["summary"] == "实际使用 7 种能力，共 87 次调用"
    direct_user = next(event for event in first["events"] if event["role"] == "user")
    assert direct_user["source_line"] == 7
    assert direct_user["codex_user_origin"] == "event_msg_mirror"


def test_report_template_defaults_to_readable_conversation_with_evidence_and_full_event_modes() -> None:
    template = (ROOT / "templates" / "golden-session-review" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'data-view-mode="conversation"' in template
    assert 'data-view-mode="evidence"' in template
    assert 'data-view-mode="all"' in template
    assert "const PAGE_SIZE = 40" in template
    assert 'id="pagePrevious"' in template
    assert 'id="pageNext"' in template
