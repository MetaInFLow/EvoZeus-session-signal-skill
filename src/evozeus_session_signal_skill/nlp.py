from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
import importlib.util
import json
import logging
import re
from typing import Any, Mapping


NLP_PACKAGES = ("scikit-learn", "jieba", "rapidfuzz", "snownlp")
INSTALL_HINT = "python3 -m pip install 'EvoZeus-session-signal-skill[nlp]'"


class MissingNlpDependencyError(RuntimeError):
    pass


def missing_nlp_dependencies() -> list[str]:
    missing = []
    for package_name, import_name in (
        ("scikit-learn", "sklearn"),
        ("jieba", "jieba"),
        ("rapidfuzz", "rapidfuzz"),
        ("snownlp", "snownlp"),
    ):
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)
    return missing


def ensure_nlp_dependencies() -> None:
    missing = missing_nlp_dependencies()
    if missing:
        raise MissingNlpDependencyError(
            "missing official factor NLP dependencies: "
            + ", ".join(missing)
            + f". Install with: {INSTALL_HINT}"
        )


try:
    import jieba
    import jieba.posseg as jieba_posseg
except ImportError:  # pragma: no cover - checked through ensure_nlp_dependencies.
    jieba = None
    jieba_posseg = None
else:
    jieba.setLogLevel(logging.ERROR)

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
except ImportError:  # pragma: no cover - checked through ensure_nlp_dependencies.
    rapidfuzz_fuzz = None

try:
    from snownlp import SnowNLP
except ImportError:  # pragma: no cover - checked through ensure_nlp_dependencies.
    SnowNLP = None


DROP_BLOCK_PATTERNS = (
    re.compile(r"```.*?```", re.S),
    re.compile(r"<image\b.*?</image>", re.S | re.I),
    re.compile(r"<environment_context>.*?</environment_context>", re.S | re.I),
    re.compile(r"<INSTRUCTIONS>.*?</INSTRUCTIONS>", re.S | re.I),
    re.compile(r"<turn_aborted>.*?</turn_aborted>", re.S | re.I),
    re.compile(r"<subagent_notification>.*?</subagent_notification>", re.S | re.I),
    re.compile(r"<goal_context>.*?</goal_context>", re.S | re.I),
)
REQUEST_MARKER_RE = re.compile(r"##\s*My request for Codex:\s*", re.I)
AUTOMATION_PATTERN = re.compile(r"^\s*Automation:|Automation ID:", re.I)
SUBAGENT_EVENT_PATTERN = re.compile(r"<subagent_notification>|subagent_notification", re.I)
DELEGATED_TASK_PATTERN = re.compile(
    r"(^|\n)\s*你是[^。\n]{0,80}(agent|worker|研究员|审查|实施计划|任务)"
    r"|你不孤立在代码库里"
    r"|请只读检查仓库"
    r"|只读检查\s*/Users/"
    r"|本轮\s*SKILL\s*架构调研的子任务研究员",
    re.I,
)
DIRECT_USER_SCOPES = {"", "direct_user", "context_wrapper"}
CODEX_REAL_USER_ORIGINS = {"", "event_msg", "event_msg_mirror", "response_item_mirror"}
CODEX_CONTEXT_USER_ORIGINS = {"synthetic_context"}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
SENTENCE_SPLIT_RE = re.compile(r"[\n\r\t。！？!?；;，,、：:]+")
LEADING_MARKDOWN_RE = re.compile(r"^\s*(?:[-*+>]\s+|#{1,6}\s+|\d+[.)]\s+)")
PATH_OR_URL_RE = re.compile(r"(?:https?://|^//|/Users/|/var/folders|\.jsonl\b|[/\\][\w.-]+[/\\]?)", re.I)
FILE_TOKEN_RE = re.compile(
    r"^[\w./-]+\.(?:md|tsx?|jsx?|py|json|ya?ml|xml|png|jpe?g|svg|mjs|css|toml|lock)$",
    re.I,
)
LONG_BASE64ISH_RE = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,4}|[A-Za-z][A-Za-z0-9_-]*")
HAS_TEXT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z]")
NATURAL_TEXT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z]")
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
LOG_MARKER_RE = re.compile(r"\b(?:traceback|exception|error|failed|failure|exit code|stderr|pytest|npm err|warning)\b", re.I)
JSONISH_LINE_RE = re.compile(r"^\s*[\[{]|[{}\[\]\":,]{4,}")
LOW_VALUE_TEXT = {"继续", "开始", "好的", "收到", "可以", "ok", "yes", "no", "嗯", "好"}
NOISE_EXACT = {
    "http",
    "https",
    "agent_path",
    "completed",
    "status",
    "incomplete",
    "index",
    "project",
    "text",
    "true",
    "false",
    "null",
    "payload",
    "type",
}
NOISE_SUBSTRINGS = {
    "agents.md",
    "environment_context",
    "workspace_roots",
    "permission_profile",
    "filesystem",
    "project-doc",
    "files mentioned by the user",
    "codex-clipboard",
    "continue working toward the active thread goal",
    "objective below is user-provided data",
    "not as higher-priority instructions",
}


@dataclass(frozen=True)
class ClassifiedText:
    label: str
    score: float
    confidence: float
    nearest_example: str
    snownlp_score: float


@dataclass(frozen=True)
class SignalTextBlock:
    block_type: str
    text: str
    confidence: float
    should_feed_factor: bool
    reason: str
    features: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticPhraseCandidate:
    cluster_id: str
    label: str
    text: str


def event_factor_channel(event: Mapping[str, Any]) -> str:
    channel = str(_event_value(event, "factor_channel") or "")
    if channel:
        return channel
    role = str(_event_value(event, "role") or "")
    if role == "user":
        return "user_input"
    if role == "assistant":
        return "assistant_result"
    if role == "tool":
        event_type = str(event.get("codex_event_type") or "")
        if event_type in {"function_call", "custom_tool_call", "web_search_call"}:
            return "tool_usage"
        return "tool_result"
    if role == "task_complete":
        return "assistant_result"
    return "context"


def event_chat_role(event: Mapping[str, Any]) -> str:
    chat_role = str(_event_value(event, "chat_role") or "")
    if chat_role:
        return chat_role
    channel = event_factor_channel(event)
    if channel == "user_input":
        return "user"
    if channel == "assistant_result":
        return "assistant"
    if channel in {"tool_usage", "tool_result"}:
        return "tool"
    return "context"


def channel_events(events: Iterable[Mapping[str, Any]], channels: set[str]) -> list[Mapping[str, Any]]:
    return [event for event in events if event_factor_channel(event) in channels]


def event_message_scope(event_or_text: Mapping[str, Any] | str) -> str:
    if isinstance(event_or_text, Mapping):
        lineage_scope = _session_lineage_message_scope(event_or_text)
        if lineage_scope:
            return lineage_scope
        origin = str(_event_value(event_or_text, "codex_user_origin") or "")
        if origin in CODEX_CONTEXT_USER_ORIGINS:
            return "context_wrapper"
        explicit = str(_event_value(event_or_text, "message_scope") or "")
        if explicit:
            return explicit
        value = str(_event_value(event_or_text, "factor_text") or _event_value(event_or_text, "text") or "")
    else:
        value = str(event_or_text)
    text = value.strip()
    if not text:
        return "empty"
    if SUBAGENT_EVENT_PATTERN.search(text):
        return "subagent_event"
    if AUTOMATION_PATTERN.search(text):
        return "automation"
    if DELEGATED_TASK_PATTERN.search(text):
        return "delegated_task"
    if REQUEST_MARKER_RE.search(text):
        return "context_wrapper"
    return "direct_user"


def is_direct_user_input(event: Mapping[str, Any]) -> bool:
    if event_factor_channel(event) != "user_input":
        return False
    if _session_lineage_message_scope(event):
        return False
    origin = str(_event_value(event, "codex_user_origin") or "")
    if origin in CODEX_CONTEXT_USER_ORIGINS:
        return False
    if origin not in CODEX_REAL_USER_ORIGINS:
        return False
    return event_message_scope(event) in DIRECT_USER_SCOPES


def direct_user_events(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [event for event in events if is_direct_user_input(event)]


def canonical_text(event_or_text: Mapping[str, Any] | str) -> str:
    value = _raw_text(event_or_text)
    if not value:
        return ""

    marker = REQUEST_MARKER_RE.search(value)
    if marker is not None:
        value = value[marker.end() :]
    elif value.lower().lstrip().startswith("# agents.md instructions"):
        return ""
    elif value.lower().lstrip().startswith("# context from my ide setup"):
        return ""

    if _looks_like_image_payload(value):
        return ""

    value = _strip_drop_blocks(value)
    value = MARKDOWN_LINK_RE.sub(" ", value)

    lines = []
    skip_files_section = False
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("# files mentioned by the user"):
            skip_files_section = True
            continue
        if skip_files_section and lowered.startswith("## codex-clipboard-"):
            continue
        if line.startswith("<") and line.endswith(">"):
            continue
        lines.append(line)
        skip_files_section = False
    return "\n".join(lines).strip()


def signal_text(event_or_text: Mapping[str, Any] | str, *, min_len: int = 2, max_len: int = 5000) -> str:
    texts: list[str] = []
    for block in classify_signal_text(event_or_text, max_len=max_len):
        if not block.should_feed_factor:
            continue
        compact = "".join(block.text.split())
        if min_len <= len(compact) <= max_len:
            texts.append(block.text)
    return "\n".join(texts).strip()


def classify_signal_text(event_or_text: Mapping[str, Any] | str, *, max_len: int = 5000) -> list[SignalTextBlock]:
    if _is_context_mapping(event_or_text):
        value = str(event_or_text.get("factor_text") or event_or_text.get("text") or "")
        return [_block("context_block", "", False, "event factor channel is context", _text_features(value), confidence=0.95)]

    value = _raw_text(event_or_text)
    if not value:
        return []

    scoped = _request_scope(value)
    if not scoped:
        return []
    if _looks_like_image_payload(scoped):
        return [_block("media_payload", "", False, "image/base64 payload", _text_features(scoped), confidence=0.95)]

    scoped = MARKDOWN_LINK_RE.sub(" ", scoped)
    blocks: list[SignalTextBlock] = []
    for segment, is_code in _split_code_fence_segments(scoped):
        if is_code:
            blocks.append(_block("code_paste", "", False, "markdown code fence", _text_features(segment), confidence=0.92))
            continue
        segment = _clean_segment(segment)
        if not segment:
            continue

        features = _text_features(segment)
        block_type, reason, should_feed = _classify_block(segment, features)
        if should_feed:
            text = segment[:max_len].strip()
            blocks.append(_block(block_type, text, True, reason, features, confidence=0.86))
            continue

        excerpt = _natural_request_excerpt(segment, max_len=max_len)
        if excerpt:
            blocks.append(_block("request_text", excerpt, True, "natural-language prefix/suffix around pasted content", _text_features(excerpt), confidence=0.82))
        blocks.append(_block(block_type, "", False, reason, features, confidence=0.86))
    return _dedupe_signal_blocks(blocks)


def normalized_clause(value: str) -> str:
    value = value.replace("\\n", " ")
    value = LEADING_MARKDOWN_RE.sub("", value).strip()
    value = value.strip("` \"'“”‘’()[]{}<>《》")
    value = " ".join(value.split())
    value = value.replace("合理利用subagent", "合理利用 subagent")
    return value.strip()


def sentence_candidates(value: str, *, min_len: int = 2, max_len: int = 80, include_low_value: bool = False) -> list[str]:
    text = canonical_text(value)
    if not text:
        return []
    sentences: list[str] = []
    seen: set[str] = set()
    for segment in SENTENCE_SPLIT_RE.split(text):
        sentence = normalized_clause(segment)
        if not sentence:
            continue
        if not include_low_value and sentence.lower() in LOW_VALUE_TEXT:
            continue
        if not is_text_signal(sentence, min_len=min_len, max_len=max_len):
            continue
        if sentence in seen:
            continue
        seen.add(sentence)
        sentences.append(sentence)
    return sentences


def authored_request_text(event_or_text: Mapping[str, Any] | str) -> str:
    text = signal_text(event_or_text)
    if not text:
        return ""
    lines: list[str] = []
    for index, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        if index > 0 and _starts_pasted_section(line):
            break
        if _looks_like_shell_line(line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def semantic_phrase_candidates(event_or_text: Mapping[str, Any] | str) -> list[SemanticPhraseCandidate]:
    authored_text = authored_request_text(event_or_text)
    rule_text = canonical_text(event_or_text) or authored_text
    if not rule_text:
        return []
    candidates: list[SemanticPhraseCandidate] = []
    seen_clusters: set[str] = set()
    for cluster_id, label, patterns in SEMANTIC_INTENT_RULES:
        for pattern in patterns:
            match = pattern.search(rule_text)
            if match is None:
                continue
            phrase = normalized_clause(match.groupdict().get("phrase") or match.group(0))
            if phrase:
                candidates.append(SemanticPhraseCandidate(cluster_id, label, phrase))
                seen_clusters.add(cluster_id)
            break

    seen: set[tuple[str, str]] = {(candidate.cluster_id, candidate.text) for candidate in candidates}
    for raw_clause in SENTENCE_SPLIT_RE.split(authored_text):
        clause = normalized_clause(raw_clause)
        if not clause:
            continue
        candidate = _semantic_phrase_candidate(clause)
        if (
            candidate is None
            or candidate.cluster_id in seen_clusters
            or (candidate.cluster_id, candidate.text) in seen
        ):
            continue
        seen.add((candidate.cluster_id, candidate.text))
        seen_clusters.add(candidate.cluster_id)
        candidates.append(candidate)
    return candidates


def semantic_request_signature(value: str) -> str:
    candidates = semantic_phrase_candidates(value)
    return candidates[0].cluster_id if candidates else ""


def is_text_signal(value: str, *, min_len: int = 2, max_len: int = 80) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if lowered in NOISE_EXACT:
        return False
    compact = "".join(value.split())
    if not min_len <= len(compact) <= max_len:
        return False
    if any(token in lowered for token in NOISE_SUBSTRINGS):
        return False
    if FILE_TOKEN_RE.match(value):
        return False
    if value.startswith(".") and value.endswith("/"):
        return False
    if PATH_OR_URL_RE.search(value):
        return False
    if not HAS_TEXT_RE.search(value):
        return False
    if _looks_like_image_payload(value):
        return False
    return True


def _semantic_phrase_candidate(clause: str) -> SemanticPhraseCandidate | None:
    compact = " ".join(clause.split()).strip()
    lowered = compact.lower()
    review_match = re.search(
        r"(?:再)?(?:review|检查|审查|评审)\s*(?:一下)?\s*(?:这些|当前|现在的)?\s*factor(?:s)?",
        compact,
        re.I,
    )
    if review_match:
        variant = " ".join(review_match.group(0).split()).replace(" factors", " factor")
        return SemanticPhraseCandidate("intent.review_factors", "检查/评审 Factor", variant)

    if "报告" in compact:
        return None
    if any(term in lowered for term in ("启动会", "启动时", "运行效果", "对外启动", "启动项目的指南")):
        return None
    if re.search(r"(?:已经|都|成功)[^。！？!?]{0,12}(?:运行|跑)起来了", lowered):
        return None
    has_project_object = any(term in lowered for term in ("项目", "tauri", "dev server", "app", "应用"))
    has_run_request = bool(
        any(term in lowered for term in ("拉起来", "跑起来", "跑一下"))
        or re.search(r"^(?:现在|先|请)?\s*(?:启动|运行)", lowered)
        or re.search(r"(?:把|将|需要你|帮我|我希望|我想要)[^。！？!?]{0,36}(?:启动|运行)", lowered)
    )
    if has_run_request and has_project_object:
        return SemanticPhraseCandidate("intent.run_project", "启动/运行项目", compact)
    return None


def _intent_pattern(value: str) -> re.Pattern[str]:
    return re.compile(value, re.I)


SEMANTIC_INTENT_RULES: tuple[tuple[str, str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "intent.clarify_positioning",
        "讲清楚产品定位",
        (
            _intent_pattern(r"(?P<phrase>(?:没有|没)呈现清楚[^，。！？!?\n]{0,36}(?:一句话)?定位(?:、功能)?)"),
            _intent_pattern(r"(?P<phrase>(?:还是)?都看不懂[，,](?:都)?不像在说人话)"),
            _intent_pattern(r"(?P<phrase>依旧不是人话[。.]\s*define\s*我们这个是什么)"),
            _intent_pattern(r"(?P<phrase>还是没体现重点)"),
        ),
    ),
    (
        "intent.expand_design_directions",
        "继续发散设计方向",
        (
            _intent_pattern(r"(?P<phrase>不好[，,]你思路打开行吗)"),
            _intent_pattern(r"(?P<phrase>方向[^，。！？!?\n]{0,18}好点[，,]但是还是很蠢很普通)"),
            _intent_pattern(r"(?P<phrase>还不好继续发散)"),
            _intent_pattern(r"(?P<phrase>\d*好一点但还不够)"),
        ),
    ),
    (
        "intent.user_value",
        "从用户视角讲清价值",
        (
            _intent_pattern(r"(?P<phrase>没看到爽点[，,]没看到自己能快速获得什么价值)"),
            _intent_pattern(r"(?P<phrase>先想一下用户人群什么人会用)"),
        ),
    ),
    (
        "intent.explain_hook_behavior",
        "解释 Hook 的触发与作用",
        (
            _intent_pattern(r"(?P<phrase>hook会注入哪些过程当前)"),
            _intent_pattern(r"(?:告诉我)?(?P<phrase>什么情况下会激活什么hook会做什么)"),
            _intent_pattern(r"(?P<phrase>这些hook的原始意图讲一下)"),
        ),
    ),
    (
        "intent.install_evozeus",
        "安装、注册并开始使用 EvoZeus",
        (
            _intent_pattern(r"(?P<phrase>加入\s+EvoZeus)"),
            _intent_pattern(r"(?P<phrase>安装、注册、开始使用)"),
        ),
    ),
    (
        "intent.concise_supplier_output",
        "输出更精简、直接可外发",
        (
            _intent_pattern(r"(?P<phrase>不要那么多背景[，,]我只要结果)"),
            _intent_pattern(r"(?P<phrase>写一个TLDR)"),
            _intent_pattern(r"(?P<phrase>不要一大段文字(?:不要类codex)?)"),
        ),
    ),
)


def _starts_pasted_section(line: str) -> bool:
    lowered = line.lower()
    return lowered.startswith(("# system prompt", "# prompt", "## system prompt", "## prompt"))


def _looks_like_shell_line(line: str) -> bool:
    return bool(
        re.search(r"(?:^|\s)(?:\([^)]*\)\s*)?\[[^\]]+@?[^\]]*\][#$]\s*", line)
        or re.search(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+[^#$]*[#$]\s*", line)
    )


@lru_cache(maxsize=20000)
def tokens(value: str) -> tuple[str, ...]:
    ensure_nlp_dependencies()
    if jieba is not None:
        parts = [part.strip().lower() for part in jieba.cut(value) if part.strip()]
        return tuple(part for part in parts if HAS_TEXT_RE.search(part))
    return tuple(_fallback_tokens(value))


def pos_tokens(value: str) -> list[tuple[str, str]]:
    ensure_nlp_dependencies()
    if jieba_posseg is not None:
        return [
            (word.strip(), flag)
            for word, flag in jieba_posseg.cut(value)
            if word.strip() and HAS_TEXT_RE.search(word)
        ]
    return [(token, "") for token in _fallback_tokens(value)]


def similarity(a: str, b: str) -> float:
    ensure_nlp_dependencies()
    if not a or not b:
        return 0.0
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(" ".join(tokens(a)), " ".join(tokens(b)))) / 100.0
    a_tokens = set(_fallback_tokens(a))
    b_tokens = set(_fallback_tokens(b))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))


def classify_by_examples(text: str, examples_by_label: Mapping[str, list[str]]) -> ClassifiedText:
    ensure_nlp_dependencies()
    from sklearn.metrics.pairwise import cosine_similarity

    text = text[:600]
    signature = tuple((label, tuple(values)) for label, values in examples_by_label.items())
    labels, examples, vectorizer, example_matrix = _example_model(signature)
    text_matrix = vectorizer.transform([text])
    scores = cosine_similarity(text_matrix, example_matrix).flatten()
    best_index = int(scores.argmax()) if len(scores) else 0
    best_score = float(scores[best_index]) if len(scores) else 0.0
    label = labels[best_index] if labels else "unknown"
    snownlp_score = snow_sentiment(text)
    confidence = min(0.95, 0.45 + best_score * 0.8)
    return ClassifiedText(
        label=label,
        score=round(best_score, 4),
        confidence=round(confidence, 4),
        nearest_example=examples[best_index] if examples else "",
        snownlp_score=round(snownlp_score, 4),
    )


@lru_cache(maxsize=32)
def _example_model(signature: tuple[tuple[str, tuple[str, ...]], ...]):
    from sklearn.feature_extraction.text import TfidfVectorizer

    labels: list[str] = []
    examples: list[str] = []
    for label, values in signature:
        for value in values:
            labels.append(label)
            examples.append(value)
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    example_matrix = vectorizer.fit_transform(examples)
    return labels, examples, vectorizer, example_matrix


@lru_cache(maxsize=20000)
def snow_sentiment(text: str) -> float:
    ensure_nlp_dependencies()
    if SnowNLP is None:
        return 0.5
    text = text[:120]
    try:
        return float(SnowNLP(text).sentiments)
    except Exception:
        return 0.5


def safe_json_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, Mapping) else {}
    return {}


def _event_value(event: Mapping[str, Any], key: str) -> Any:
    if key in event:
        return event.get(key)
    metadata = event.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return ""


def _session_lineage_message_scope(event: Mapping[str, Any]) -> str:
    thread_source = str(_event_value(event, "session_thread_source") or "")
    source_kind = str(_event_value(event, "session_source_kind") or "")
    parent_thread_id = str(_event_value(event, "subagent_parent_thread_id") or "")
    if thread_source == "automation":
        return "automation"
    if thread_source == "subagent" or source_kind == "subagent" or parent_thread_id:
        return "delegated_task"
    return ""


def _raw_text(event_or_text: Mapping[str, Any] | str) -> str:
    if isinstance(event_or_text, Mapping):
        if event_factor_channel(event_or_text) == "context":
            return ""
        value = str(_event_value(event_or_text, "factor_text") or _event_value(event_or_text, "text") or "")
    else:
        value = str(event_or_text)
    return value.replace("\\n", "\n").strip()


def _is_context_mapping(value: Mapping[str, Any] | str) -> bool:
    return isinstance(value, Mapping) and event_factor_channel(value) == "context"


def _request_scope(value: str) -> str:
    value = value.strip()
    marker = REQUEST_MARKER_RE.search(value)
    if marker is not None:
        value = value[marker.end() :]
    elif value.lower().lstrip().startswith("# agents.md instructions"):
        return ""
    elif value.lower().lstrip().startswith("# context from my ide setup"):
        return ""
    return value[:5000].strip()


def _strip_drop_blocks(value: str) -> str:
    for pattern in DROP_BLOCK_PATTERNS:
        value = pattern.sub(" ", value)
    return value


def _split_code_fence_segments(value: str) -> list[tuple[str, bool]]:
    segments: list[tuple[str, bool]] = []
    cursor = 0
    for match in CODE_FENCE_RE.finditer(value):
        if match.start() > cursor:
            segments.append((value[cursor : match.start()], False))
        segments.append((match.group(0), True))
        cursor = match.end()
    if cursor < len(value):
        segments.append((value[cursor:], False))
    return segments or [(value, False)]


def _clean_segment(value: str) -> str:
    value = _strip_drop_blocks(value)
    lines = []
    skip_files_section = False
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("# files mentioned by the user"):
            skip_files_section = True
            continue
        if skip_files_section and lowered.startswith("## codex-clipboard-"):
            continue
        if line.startswith("<") and line.endswith(">"):
            continue
        lines.append(line)
        skip_files_section = False
    return "\n".join(lines).strip()


def _text_features(value: str) -> dict[str, float]:
    lines = [line for line in value.splitlines() if line.strip()] or [value]
    char_count = len(value)
    non_space_count = sum(1 for char in value if not char.isspace())
    longest_line = max((len(line) for line in lines), default=0)
    path_or_url_lines = sum(1 for line in lines if PATH_OR_URL_RE.search(line))
    file_extension_lines = sum(1 for line in lines if FILE_TOKEN_RE.search(line.strip()))
    log_marker_lines = sum(1 for line in lines if LOG_MARKER_RE.search(line))
    jsonish_lines = sum(1 for line in lines if JSONISH_LINE_RE.search(line))
    base64_chars = sum(len(match.group(0)) for match in LONG_BASE64ISH_RE.finditer(value))
    repeated_lines = len(lines) - len(set(line.strip() for line in lines))
    symbol_chars = sum(1 for char in value if not char.isspace() and not char.isalnum() and not re.search(r"[\u4e00-\u9fff]", char))
    natural_chars = sum(1 for char in value if NATURAL_TEXT_RE.search(char))
    denominator = float(max(1, len(lines)))
    char_denominator = float(max(1, non_space_count))
    return {
        "char_count": float(char_count),
        "line_count": float(len(lines)),
        "avg_line_length": float(char_count) / denominator,
        "longest_line_length": float(longest_line),
        "code_fence_count": float(value.count("```") // 2),
        "json_like_ratio": float(jsonish_lines) / denominator,
        "path_or_url_ratio": float(path_or_url_lines) / denominator,
        "file_extension_ratio": float(file_extension_lines) / denominator,
        "log_marker_ratio": float(log_marker_lines) / denominator,
        "base64_ratio": float(base64_chars) / float(max(1, char_count)),
        "repeated_line_ratio": float(repeated_lines) / denominator,
        "symbol_ratio": float(symbol_chars) / char_denominator,
        "natural_language_ratio": float(natural_chars) / char_denominator,
    }


def _classify_block(value: str, features: Mapping[str, float]) -> tuple[str, str, bool]:
    lowered = value.lower().strip()
    if not lowered:
        return "empty", "empty segment", False
    if lowered in LOW_VALUE_TEXT:
        return "low_value_reply", "low-value short reply", False
    if _looks_like_image_payload(value):
        return "media_payload", "image/base64 payload", False
    if features["base64_ratio"] > 0.05:
        return "media_payload", "base64-like payload", False
    if features["code_fence_count"] > 0:
        return "code_paste", "markdown code fence", False
    if features["log_marker_ratio"] >= 0.18 or "traceback" in lowered:
        return "log_paste", "log/error markers dominate", False
    if features["json_like_ratio"] >= 0.35:
        return "pasted_context", "json-like pasted content", False
    if features["path_or_url_ratio"] >= 0.25 or features["file_extension_ratio"] >= 0.25:
        return "pasted_context", "path/file-list pasted content", False
    if features["char_count"] > 2000 and features["line_count"] > 20 and features["natural_language_ratio"] < 0.6:
        return "pasted_context", "large pasted block with low natural-language density", False
    if not is_text_signal(value, max_len=5000):
        return "pasted_context", "not a valid text signal", False
    return "request_text", "natural-language request", True


def _natural_request_excerpt(value: str, *, max_len: int) -> str:
    lines = [normalized_clause(line) for line in value.splitlines()]
    candidates = []
    for line in [*lines[:8], *lines[-8:]]:
        if not line or line.lower() in LOW_VALUE_TEXT:
            continue
        features = _text_features(line)
        block_type, _, should_feed = _classify_block(line, features)
        if should_feed and block_type == "request_text":
            candidates.append(line)
    excerpt = "\n".join(dict.fromkeys(candidates))
    return excerpt[:max_len].strip()


def _block(
    block_type: str,
    text: str,
    should_feed_factor: bool,
    reason: str,
    features: Mapping[str, float],
    *,
    confidence: float,
) -> SignalTextBlock:
    return SignalTextBlock(
        block_type=block_type,
        text=text,
        confidence=confidence,
        should_feed_factor=should_feed_factor,
        reason=reason,
        features={key: round(float(value), 4) for key, value in features.items()},
    )


def _dedupe_signal_blocks(blocks: list[SignalTextBlock]) -> list[SignalTextBlock]:
    deduped: list[SignalTextBlock] = []
    seen_feed_text: set[str] = set()
    for block in blocks:
        if block.should_feed_factor:
            key = " ".join(block.text.split())
            if key in seen_feed_text:
                continue
            seen_feed_text.add(key)
        deduped.append(block)
    return deduped


def _looks_like_image_payload(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if "data:image" in lowered or '"image_url"' in lowered or "image_url" in lowered and "base64" in lowered:
        return True
    return "base64" in lowered and LONG_BASE64ISH_RE.search(value) is not None


def _fallback_tokens(value: str) -> list[str]:
    found = [token.lower() for token in TOKEN_RE.findall(value)]
    if len(found) > 1:
        return found
    compact = "".join(value.split()).lower()
    if re.search(r"[\u4e00-\u9fff]", compact):
        return [compact[index : index + 2] for index in range(max(1, len(compact) - 1))]
    return found
