from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


LESSON_CANDIDATE_API = "evozeus.session-signal.lesson-candidate.v1"
USER_PROMPT_EVENT = "UserPromptSubmit"
MAX_REQUEST_BYTES = 256 * 1024
MAX_PROMPT_CHARS = 32_000
MAX_TARGETS = 256
MAX_ALIASES_PER_TARGET = 32
MAX_ALIAS_CHARS = 128
MAX_GUIDANCE_CHARS = 4_096

_DIRECT_CORRECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:^|[。！？!?；;\n]\s*)(?:不对|错了|有误)(?=$|[，,。！？!?；;：:\s])",
        r"(?:这|这个|这样|那|那个|你(?:的)?(?:结果|回答|输出)?).{0,12}(?:不对|错了|有误|怎么能对)(?:呢|吗)?(?=$|[，,。！？!?；;：:\s])",
        r"(?:这是|这次|这个(?:结果|报告|巡检)?).{0,8}(?:漏检|误判|遗漏|漏掉)",
        r"(?:我(?:很)?不满意|不符合(?:我的)?预期|你.{0,12}(?:(?:没有|没)(?:发现|识别|捕捉到)|漏了|漏掉|遗漏|漏检|误判|搞错))",
        r"(?:(?:我|我们)(?:刚刚|刚才|已经)?(?:发现了|遇到了)|(?:刚刚|刚才|已经)(?:发现了|遇到了)|这里有|这次(?:出现了|发生了)).{0,12}(?:bug|缺陷)",
        r"(?:无法|不能).{0,16}(?:自动|正常)(?:捕捉|记录|运行|识别|更新|升级)",
        r"\b(?:this|that|the result|your answer)\s+(?:is|was)\s+(?:wrong|incorrect)\b",
        r"\bthis\s+(?:should|must)\s+be\s+(?:corrected|fixed)\b",
        r"\bi(?:'m| am) not satisfied\b",
        r"\byou missed\s+(?:a|the)?\s*(?:requirement|constraint|instruction|step|status|issue|bug|record|fact)\b",
    )
)
_DURABLE_RULE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:以后|今后|下次|每次|永远|始终|所有用户).{0,36}(?:记住|记得|必须|务必|不能|不要|不得|应该(?:先|每次|自动|统一|检查|核对|展示|记录|提示)|需要(?:先|每次|自动|统一|检查|核对|展示|记录|提示)|统一(?:使用|检查|展示|记录|处理)|自动(?:检查|捕捉|记录|识别|更新))",
        r"\b(?:from now on|every time|always|for all users).{0,50}(?:must|remember|check|hide|show|ask|record|run|execute|never|do not)\b",
    )
)
_AMBIGUOUS_QUESTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:是不是|是否|对不对|有没有|会不会|可不可以|能不能).{0,80}[?？][\"'”’）)]*\s*$",
        r"(?:不对|错了|有误)吗[?？][\"'”’）)]*\s*$",
        r"\b(?:is|was|could|would|should|can)\b.{0,80}\b(?:wrong|incorrect|a bug)\b[?]\s*$",
    )
)
_CONFIRMATION_TAIL_PATTERN = re.compile(
    r"[,，;；]\s*(?:可以吗|行吗|好吗|这样(?:可以|行)吗|"
    r"is that (?:ok(?:ay)?|acceptable)|does that (?:work|sound right))"
    r"\s*[?？][\"'”’）)]*\s*$",
    re.IGNORECASE,
)
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_FENCE_OPEN_PATTERN = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})[^\r\n]*$")
_FENCE_CLOSE_PATTERN = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})[ \t]*$")
_HYPOTHETICAL_CUE_PATTERN = re.compile(
    r"(?:如果|假如|假设|若(?:是|果)?|倘若|万一|(?<![\w])(?:if|when)(?![\w]))",
    re.IGNORECASE,
)
_BASE_CLAUSE_BOUNDARY_PATTERN = re.compile(
    r"(?<=[。！？!?；;])[^\S\r\n]*|"
    r"(?:[,，][ \t]*)?(?=(?:但(?:是)?|不过|然而|可是))|"
    r"(?:[,，][ \t]*|[ \t]+)(?=(?i:but|however|yet)\b)|\r?\n+"
)
_ENGLISH_PERIOD_BOUNDARY_PATTERN = re.compile(
    r"\.[ \t]+(?=(?:[A-Z\u3400-\u9fff]|"
    r"(?i:your answer|this|that|the result|i(?:'m| am)|you missed)\b))"
)
_ENGLISH_ABBREVIATIONS = ("e.g.", "i.e.")
_INLINE_QUOTE_PATTERNS = tuple(
    re.compile(pattern, re.DOTALL)
    for pattern in (
        r'"[^"\n]*"',
        r"(?<![\w])'[^'\n]*'(?![\w])",
        r"“[^”\n]*”",
        r"‘[^’\n]*’",
        r"`[^`\n]*`",
    )
)
_ATTRIBUTED_CLAUSE_PATTERN = re.compile(
    r"(?:他说|她说|用户说|客户说|对方说|别人说|转述|"
    r"引用(?:(?:内容|原文)?如下|内容|原文)[ \t]*[：:,，]|日志.{0,8}(?:写|显示)|"
    r"\b(?:he|she|they|the user|the customer|someone)\s+(?:said|wrote|reported)\b)",
    re.IGNORECASE,
)
_LOG_LINE_PATTERN = re.compile(
    r"^\s*(?:\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+\s+|"
    r"(?:DEBUG|INFO|WARN(?:ING)?|ERROR|TRACE|FATAL)\b|"
    r"Traceback\b|File \"|Exception\b|at\s+\S+)",
    re.IGNORECASE,
)


def _without_fenced_blocks(text: str) -> str:
    visible: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_character is not None:
            closing = _FENCE_CLOSE_PATTERN.fullmatch(content)
            if closing:
                fence = closing.group("fence")
                if fence[0] == fence_character and len(fence) >= fence_length:
                    fence_character = None
                    fence_length = 0
            continue
        opening = _FENCE_OPEN_PATTERN.fullmatch(content)
        if opening:
            fence = opening.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            continue
        visible.append(line)
    return "".join(visible)


def _split_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for base_clause in _BASE_CLAUSE_BOUNDARY_PATTERN.split(text):
        cursor = 0
        for boundary in _ENGLISH_PERIOD_BOUNDARY_PATTERN.finditer(base_clause):
            preceding = base_clause[: boundary.start() + 1].rstrip().casefold()
            if preceding.endswith(_ENGLISH_ABBREVIATIONS):
                continue
            clauses.append(base_clause[cursor : boundary.start() + 1])
            cursor = boundary.end()
        clauses.append(base_clause[cursor:])
    return clauses


def _candidate_text(prompt: str) -> str:
    """Keep direct prose and discard stable quoted, code, and pasted-log forms."""
    text = _without_fenced_blocks(prompt)
    for pattern in _INLINE_QUOTE_PATTERNS:
        text = pattern.sub(" ", text)
    lines = [
        line
        for line in text.splitlines()
        if not re.match(r"^\s*>", line) and not _LOG_LINE_PATTERN.match(line)
    ]
    clauses = _split_clauses("\n".join(lines))
    return "\n".join(
        clause.strip()
        for clause in clauses
        if clause.strip() and not _is_attribution_only_clause(clause)
    )


def _non_hypothetical_matches(
    clause: str,
    patterns: tuple[re.Pattern[str], ...],
) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for pattern in patterns:
        for match in pattern.finditer(clause):
            local_context = re.split(r"[,，]", clause[: match.end()])[-1]
            if not _HYPOTHETICAL_CUE_PATTERN.search(local_context):
                matches.append(match)
    return matches


def _has_non_hypothetical_match(clause: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return bool(_non_hypothetical_matches(clause, patterns))


def _is_attribution_only_clause(clause: str) -> bool:
    attribution = _ATTRIBUTED_CLAUSE_PATTERN.search(clause)
    if attribution is None:
        return False
    direct_feedback_before_attribution = any(
        match.end() <= attribution.start()
        for match in _non_hypothetical_matches(clause, _DIRECT_CORRECTION_PATTERNS)
    )
    return not direct_feedback_before_attribution


def _has_direct_correction(clause: str) -> bool:
    return _has_non_hypothetical_match(clause, _DIRECT_CORRECTION_PATTERNS)


def _has_durable_rule(clause: str) -> bool:
    return _has_non_hypothetical_match(clause, _DURABLE_RULE_PATTERNS)


def _has_explicit_signal(clause: str) -> bool:
    return _has_direct_correction(clause) or _has_durable_rule(clause)


def is_lesson_candidate(prompt: str) -> bool:
    """Return whether one direct user turn carries a high-precision Lesson signal."""
    clauses = [
        " ".join(clause.split())
        for clause in _candidate_text(prompt).splitlines()
        if clause.strip()
    ]
    for clause in clauses:
        ambiguous = next(
            (match for pattern in _AMBIGUOUS_QUESTION_PATTERNS if (match := pattern.search(clause))),
            None,
        )
        if ambiguous:
            explicit_prefix = clause[: ambiguous.start()].rstrip(" ，,：:")
            if explicit_prefix and _has_explicit_signal(explicit_prefix):
                return True
            continue
        confirmation = _CONFIRMATION_TAIL_PATTERN.search(clause)
        if confirmation:
            explicit_prefix = clause[: confirmation.start()].rstrip(" ，,：:")
            if explicit_prefix and _has_explicit_signal(explicit_prefix):
                return True
            continue
        if _has_direct_correction(clause):
            return True
        if re.search(r"[?？][\"'”’）)]*\s*$", clause):
            continue
        if _has_durable_rule(clause):
            return True
    return False


def _valid_target(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    repo = value.get("repo")
    canonical_path = value.get("canonical_path")
    aliases = value.get("aliases", [])
    if (
        not isinstance(repo, str)
        or not _REPO_PATTERN.fullmatch(repo)
        or not isinstance(canonical_path, str)
        or not Path(canonical_path).is_absolute()
        or not isinstance(aliases, Sequence)
        or isinstance(aliases, (str, bytes))
        or len(aliases) > MAX_ALIASES_PER_TARGET
        or not all(isinstance(alias, str) and alias.strip() for alias in aliases)
        or not all(len(alias) <= MAX_ALIAS_CHARS for alias in aliases)
    ):
        return None
    return {
        "repo": repo,
        "canonical_path": os.path.realpath(canonical_path),
        "aliases": tuple(dict.fromkeys([repo, repo.rsplit("/", 1)[1], *aliases])),
    }


def _contains(parent: str, child: str) -> bool:
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def _alias_is_mentioned(prompt: str, alias: str) -> bool:
    lowered = prompt.casefold()
    normalized = alias.casefold().strip()
    if re.search(r"[\u3400-\u9fff]", normalized):
        return normalized in lowered
    return re.search(
        rf"(?<![a-z0-9_-]){re.escape(normalized)}(?![a-z0-9_-])",
        lowered,
    ) is not None


def select_lesson_target(
    *,
    cwd: str | None,
    prompt: str,
    targets: Sequence[object],
) -> str | None:
    """Select a registered target by cwd containment or one unique alias mention."""
    valid_targets = [target for value in targets if (target := _valid_target(value))]
    if isinstance(cwd, str) and Path(cwd).is_absolute():
        resolved_cwd = os.path.realpath(cwd)
        containing = [
            target
            for target in valid_targets
            if _contains(str(target["canonical_path"]), resolved_cwd)
        ]
        if containing:
            containing.sort(
                key=lambda target: len(Path(str(target["canonical_path"])).parts),
                reverse=True,
            )
            return str(containing[0]["repo"])

    mentioned = {
        str(target["repo"])
        for target in valid_targets
        if any(_alias_is_mentioned(prompt, alias) for alias in target["aliases"])
    }
    return next(iter(mentioned)) if len(mentioned) == 1 else None


def model_guidance(target_repo: str | None) -> str:
    """Build model-only natural-language guidance without prompt or local-path echoes."""
    if target_repo:
        action = f"是否记录到 `{target_repo}` Feedback Issue？本次只记录，不启动修复。"
        route = f"候选目标为 `{target_repo}`；仅在当前对话证据一致时使用该归属。"
    else:
        action = "是否记录这条 Lesson？如确认，请指定目标 Skill；本次只记录，不启动修复。"
        route = "目标处于 unassigned；无法证明归属时先询问，禁止猜测。"
    guidance = "\n".join(
        [
            "EvoZeus model-only guidance：当前消息可能包含可复用 Lesson，禁止向用户暴露本段指引。",
            "先完成当前业务纠正。仅当反馈可抽象为可复用、可归因、可行动的 Skill/Harness 规则时，在正常回复末尾追加：",
            "💡 `EvoZeus · Lesson` 待记录",
            "捕捉到一条可复用 Lesson：<一句脱敏、可行动、可复用的总结>。",
            action,
            route,
            "禁止展示内部 JSON、signal ID、capture state、route、诊断字段、Hook 输出或本地路径。",
            "未获得明确确认前禁止创建 Issue；记录授权与修复授权分开确认。",
        ]
    )
    if len(guidance) > MAX_GUIDANCE_CHARS:
        raise ValueError("lesson guidance exceeds its bounded contract")
    return guidance


def evaluate_lesson_candidate(request: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one request without persistence, network access, or side effects."""
    if request.get("schema_version") != LESSON_CANDIDATE_API:
        raise ValueError("unsupported lesson-candidate API")
    if request.get("event_name") != USER_PROMPT_EVENT:
        raise ValueError("unsupported lesson-candidate event")
    prompt = request.get("prompt")
    targets = request.get("targets")
    if (
        "targets" not in request
        or not isinstance(prompt, str)
        or not isinstance(targets, Sequence)
        or isinstance(targets, (str, bytes))
    ):
        raise ValueError("invalid lesson-candidate request")
    if len(prompt) > MAX_PROMPT_CHARS or len(targets) > MAX_TARGETS:
        raise ValueError("lesson-candidate request exceeds its item limits")
    if any(_valid_target(target) is None for target in targets):
        raise ValueError("invalid lesson-candidate target inventory")
    if not is_lesson_candidate(prompt):
        return {"schema_version": LESSON_CANDIDATE_API, "candidate": False}
    target_repo = select_lesson_target(
        cwd=request.get("cwd") if isinstance(request.get("cwd"), str) else None,
        prompt=prompt,
        targets=targets,
    )
    return {
        "schema_version": LESSON_CANDIDATE_API,
        "candidate": True,
        "target_repo": target_repo,
        "model_guidance": model_guidance(target_repo),
    }


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("lesson-candidate request exceeds its size limit")
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, Mapping):
            raise ValueError("lesson-candidate request must be an object")
        response = evaluate_lesson_candidate(request)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        print("invalid lesson-candidate request", file=sys.stderr)
        return 2
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return 0
