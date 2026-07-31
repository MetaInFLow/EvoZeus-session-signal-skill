from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.lesson_candidate import (  # noqa: E402
    LESSON_CANDIDATE_API,
    MAX_ALIASES_PER_TARGET,
    MAX_ALIAS_CHARS,
    MAX_PROMPT_CHARS,
    MAX_TARGETS,
    USER_PROMPT_EVENT,
    evaluate_lesson_candidate,
    is_lesson_candidate,
    select_lesson_target,
)


@pytest.mark.parametrize(
    "prompt",
    [
        "这个结果不对，遗漏了用户明确给出的验收标准。",
        "你漏检了现有 PR 的阻塞评论，请补上。",
        "你漏检了客户说的回滚要求，请补上。",
        "客户说的回滚要求你漏检了，请补上。",
        "你漏检了回滚要求，是否可以补上？",
        "你漏检了这个要求，能补上吗？",
        "你漏检了回滚要求，怎么回事？",
        "你漏检了回滚要求：能补上吗？",
        "请看上下文\n不对",
        "我刚刚发现了一个升级 bug，需要记录这个机制缺口。",
        "以后每次提交前都必须运行完整回归并检查 diff。",
        "以后每次提交前，都必须运行完整回归。",
        "每次提交前，必须跑测试。",
        "以后每次都必须检查客户说的回滚要求。",
        "以后每次提交前都必须跑测试，是否可以？",
        "以后每次都必须跑测试，可以吗？",
        "你引用的文件有误，请更正。",
        "答案不对。",
        "回答不对。",
        "Your answer is wrong; you missed the rollback requirement.",
        "The answer is wrong.",
        "This answer is wrong.",
        "You missed the rollback requirement.",
        "Your answer is wrong, can you fix it?",
        "Your answer is wrong, why did this happen?",
        "Your answer is wrong, can you fix it or explain why?",
        "Your answer is wrong: can you fix it?",
        "This should be fixed; can you fix it?",
        "I'm not satisfied; you didn't follow the requirement.",
        "I’m not satisfied; you did not follow the requirement.",
        "From now on, always check the release boundary before tagging.",
        "For all users, show status.",
        "From now on, always run tests, is that okay?",
        "Someone said the old answer was acceptable. Your answer is wrong.",
        "Someone said the old answer was acceptable. your answer is wrong.",
        "Your answer is wrong, but someone said the old answer was acceptable.",
        "Someone said the old answer was acceptable, but your answer is wrong.",
        "Someone said the old answer was okay, your answer is wrong.",
        "这个结果不对，但客户说旧版才是对的。",
        "客户说旧版才是对的，但这个结果不对。",
        "客户说旧版没问题，你的结果不对。",
        "If cost permits, from now on always run tests.",
        "假设只讨论预算，今后每次都必须检查 diff。",
        (
            'Traceback (most recent call last):\n  File "test.py", line 1, in <module>\n'
            "AssertionError: your answer is wrong\n"
            "Your answer is wrong; you missed the rollback requirement."
        ),
        (
            'Traceback (most recent call last):\n  File "test.py", line 1, in <module>\n'
            "__main__.Oops: bad\nYour answer is wrong."
        ),
        "AssertionError: quoted failure\nYour answer is wrong.",
        "[ERROR] quoted failure\nYour answer is wrong.",
        "[2026-07-31 12:00:00] [ERROR] quoted failure\nYour answer is wrong.",
        "At this point, your answer is wrong.",
    ],
)
def test_high_precision_correction_and_durable_rule_detection(prompt: str) -> None:
    assert is_lesson_candidate(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        "请总结这份报告。",
        "这个结果是不是不对？",
        "这个结果不对吗？",
        "是否有 Bug？",
        "Should this answer be considered incorrect?",
        "以后应该怎么做？",
        "帮我检查 PR 状态。",
        "请帮我发现并修复这个 bug。",
        "以后每次都必须跑测试吗？",
        "From now on, always check tests?",
        "如果这个结果不对，请重新运行。",
        "假如你的回答错了，请重新运行。",
        "If your answer is wrong, rerun it.",
        "Please rerun when the result is incorrect.",
        "假设今后每次都必须检查 diff，我们需要评估成本。",
        "If from now on we must always run tests, update the estimate.",
        "如果以后每次提交前，都必须运行测试，请先估算成本。",
        "你漏检了这个要求吗？",
        "这是漏检吗？",
        "This should be fixed?",
        "你漏检了这个要求吗，能补上吗？",
        "是你漏检了回滚要求，还是我理解错了？",
        "Your answer is wrong, or am I misunderstanding it?",
        "Your answer is wrong; or am I misunderstanding it?",
        "是你漏检了回滚要求；还是我理解错了？",
    ],
)
def test_neutral_and_ambiguous_prompts_do_not_trigger(prompt: str) -> None:
    assert is_lesson_candidate(prompt) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "如果你需要更多背景，这个结果不对。",
        "这个结果不对，如果需要我可以补充日志。",
        "If you need more context, your answer is wrong.",
        "Your answer is wrong; when needed, I can provide the logs.",
    ],
)
def test_direct_corrections_outside_conditional_scope_still_trigger(prompt: str) -> None:
    assert is_lesson_candidate(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        '请分析这句话："your answer is wrong"。',
        "Please analyze 'your answer is wrong' as wording.",
        "引用如下：\n> 这个结果错了，请修改。\n请分析语气。",
        "引用如下：这个结果错了，请分析语气。",
        "```text\nyour answer is wrong\n```\n请总结代码块。",
        "````text\nyour answer is wrong\n````\n请总结代码块。",
        "~~~~text\nyour answer is wrong\n~~~~~\n请总结代码块。",
        (
            "````markdown\n```python\nyour answer is wrong\n```\n"
            "~~~~\nthis result is wrong\n~~~~\n`````\n请总结嵌套围栏。"
        ),
        "ERROR your answer is wrong\n请分析这段日志。",
        "客户说这个结果错了，请帮我归纳客户原话。",
        "张三说你的结果不对，请总结他的反馈。",
        "Someone said your answer is wrong; summarize their feedback.",
        "The reviewer said the answer is wrong; summarize that feedback.",
        "A release manager reported you missed the rollback requirement; summarize it.",
        "Someone said the answer is wrong; summarize their feedback.",
        "Someone said you missed the rollback requirement; summarize their feedback.",
        "Someone said your answer is wrong. Please summarize that feedback.",
        "Someone said e.g. your answer is wrong; summarize the quoted example.",
        "Someone said i.e. this result is wrong. Please summarize the wording.",
        "客户说以后每次都必须检查测试，请总结这条规则。",
        "Someone wrote: “I’m not satisfied”; summarize the quotation.",
        (
            'Traceback (most recent call last):\n  File "test.py", line 1, in <module>\n'
            "    assert answer == expected\nAssertionError: your answer is wrong\n"
            "请分析这段 traceback。"
        ),
        (
            'Traceback (most recent call last):\n  File "test.py", line 1, in <module>\n'
            "    raise Oops('bad')\n__main__.Oops: your answer is wrong\n"
            "请分析这段 traceback。"
        ),
        "AssertionError: your answer is wrong\n请分析这条异常日志。",
        "[ERROR] your answer is wrong\n请分析这条日志。",
        "[2026-07-31 12:00:00] [ERROR] your answer is wrong\n请分析这条日志。",
        "2026-07-31 12:00:00,000 ERROR your answer is wrong\n请分析这条日志。",
        "at com.example.Handler.run(Handler.java:42)\n请分析这条堆栈。",
    ],
)
def test_quoted_code_log_and_attributed_corrections_do_not_trigger(prompt: str) -> None:
    assert is_lesson_candidate(prompt) is False


def _target(repo: str, canonical_path: Path, *aliases: str) -> dict[str, object]:
    return {
        "repo": repo,
        "canonical_path": str(canonical_path),
        "aliases": list(aliases),
    }


def test_target_selection_prefers_deepest_cwd_containment(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    nested = outer / "nested"

    selected = select_lesson_target(
        cwd=str(nested / "src"),
        prompt="这个结果不对。",
        targets=[
            _target("MetaInFlow/outer", outer, "outer"),
            _target("MetaInFlow/nested", nested, "nested"),
        ],
    )

    assert selected == "MetaInFlow/nested"


def test_target_selection_uses_only_one_unique_alias(tmp_path: Path) -> None:
    targets = [
        _target("MetaInFlow/alpha", tmp_path / "alpha", "Alpha Skill"),
        _target("MetaInFlow/beta", tmp_path / "beta", "Beta Skill"),
    ]

    assert (
        select_lesson_target(
            cwd=None,
            prompt="Beta Skill 的结果不对。",
            targets=targets,
        )
        == "MetaInFlow/beta"
    )
    assert (
        select_lesson_target(
            cwd=None,
            prompt="Alpha Skill 和 Beta Skill 都漏检了。",
            targets=targets,
        )
        is None
    )


def test_target_selection_leaves_colliding_alias_unassigned(tmp_path: Path) -> None:
    targets = [
        _target("MetaInFlow/alpha", tmp_path / "alpha", "shared"),
        _target("MetaInFlow/beta", tmp_path / "beta", "shared"),
    ]

    assert (
        select_lesson_target(
            cwd="relative/path",
            prompt="shared 的结果不对。",
            targets=targets,
        )
        is None
    )


def test_target_selection_does_not_infer_unregistered_repo_basename(
    tmp_path: Path,
) -> None:
    targets = [_target("MetaInFlow/api", tmp_path / "api")]

    assert (
        select_lesson_target(
            cwd=None,
            prompt="Your answer is wrong; the API omitted a field.",
            targets=targets,
        )
        is None
    )
    assert (
        select_lesson_target(
            cwd=None,
            prompt="MetaInFlow/api 的结果不对。",
            targets=targets,
        )
        == "MetaInFlow/api"
    )


def test_candidate_response_is_model_only_and_does_not_echo_prompt_or_local_path(
    tmp_path: Path,
) -> None:
    prompt = "这个结果不对，PRIVATE-PROMPT-MARKER 被遗漏了。"
    local_path = tmp_path / "private-target"

    response = evaluate_lesson_candidate(
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": prompt,
            "cwd": str(local_path / "src"),
            "targets": [_target("MetaInFlow/example", local_path, "example")],
        }
    )
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["candidate"] is True
    assert response["target_repo"] == "MetaInFlow/example"
    assert "model-only" in response["model_guidance"]
    assert "只记录，不启动修复" in response["model_guidance"]
    assert "PRIVATE-PROMPT-MARKER" not in serialized
    assert str(local_path) not in serialized
    assert "signal_id" not in serialized


def test_neutral_response_has_no_guidance() -> None:
    assert evaluate_lesson_candidate(
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": "请继续当前任务。",
            "cwd": None,
            "targets": [],
        }
    ) == {"schema_version": LESSON_CANDIDATE_API, "candidate": False}


def test_cli_reads_stdin_json_and_creates_no_runtime_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    request = {
        "schema_version": LESSON_CANDIDATE_API,
        "event_name": USER_PROMPT_EVENT,
        "prompt": "以后每次都必须先检查验收标准。",
        "cwd": str(work),
        "targets": [],
    }

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate_lesson_candidate.py")],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=work,
        env={
            **os.environ,
            "HOME": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        check=False,
    )
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    response = json.loads(result.stdout)

    assert result.returncode == 0
    assert result.stderr == ""
    assert response["schema_version"] == LESSON_CANDIDATE_API
    assert response["candidate"] is True
    assert before == after


def test_cli_rejects_invalid_input_without_echoing_it(tmp_path: Path) -> None:
    marker = "PRIVATE-INVALID-REQUEST"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate_lesson_candidate.py")],
        input=f'{{"prompt":"{marker}"',
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "invalid lesson-candidate request\n"
    assert marker not in result.stderr


def test_api_rejects_non_user_prompt_event() -> None:
    with pytest.raises(ValueError, match="event"):
        evaluate_lesson_candidate(
            {
                "schema_version": LESSON_CANDIDATE_API,
                "event_name": "SessionStart",
                "prompt": "这个结果错了。",
                "targets": [],
            }
        )


def test_api_requires_explicit_target_inventory() -> None:
    with pytest.raises(ValueError, match="invalid lesson-candidate request"):
        evaluate_lesson_candidate(
            {
                "schema_version": LESSON_CANDIDATE_API,
                "event_name": USER_PROMPT_EVENT,
                "prompt": "这个结果错了。",
            }
        )

    response = evaluate_lesson_candidate(
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": "这个结果错了。",
            "targets": [],
        }
    )
    assert response["candidate"] is True
    assert response["target_repo"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": "x" * (MAX_PROMPT_CHARS + 1),
            "targets": [],
        },
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": "这个结果错了。",
            "targets": [{}] * (MAX_TARGETS + 1),
        },
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": "这个结果错了。",
            "targets": [
                {
                    "repo": "MetaInFlow/example",
                    "canonical_path": "/tmp/example",
                    "aliases": ["alias"] * (MAX_ALIASES_PER_TARGET + 1),
                }
            ],
        },
        {
            "schema_version": LESSON_CANDIDATE_API,
            "event_name": USER_PROMPT_EVENT,
            "prompt": "这个结果错了。",
            "targets": [
                {
                    "repo": "MetaInFlow/example",
                    "canonical_path": "/tmp/example",
                    "aliases": ["x" * (MAX_ALIAS_CHARS + 1)],
                }
            ],
        },
    ],
    ids=["prompt", "targets", "aliases", "alias-length"],
)
def test_api_enforces_bounded_scan_inputs(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        evaluate_lesson_candidate(payload)


def test_api_contract_excludes_distribution_and_checksum_ownership() -> None:
    contract = json.loads(
        (ROOT / "contracts/lesson-candidate-api-v1.json").read_text(encoding="utf-8")
    )

    assert contract == {
        "schema_version": "evozeus.session-signal.lesson-candidate-api-contract.v1",
        "api": LESSON_CANDIDATE_API,
        "event_name": USER_PROMPT_EVENT,
        "transport": "stdin_stdout_json",
        "request": {
            "required": ["schema_version", "event_name", "prompt", "targets"],
            "optional": ["cwd"],
            "limits": {
                "request_bytes": 262144,
                "prompt_chars": MAX_PROMPT_CHARS,
                "targets": MAX_TARGETS,
                "aliases_per_target": MAX_ALIASES_PER_TARGET,
                "alias_chars": MAX_ALIAS_CHARS,
            },
        },
        "response": {
            "neutral_fields": ["schema_version", "candidate"],
            "candidate_fields": [
                "schema_version",
                "candidate",
                "target_repo",
                "model_guidance",
            ],
        },
        "side_effects": {"persistence": False, "network": False},
    }
    serialized = json.dumps(contract, sort_keys=True)
    assert "sha256" not in serialized
    assert "component_version" not in contract
    assert "entrypoint" not in contract
