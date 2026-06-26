from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
import importlib.util
import json
import logging
import re
from typing import Any, Mapping


NLP_PACKAGES = ("scikit-learn", "jieba", "rapidfuzz", "snownlp")
INSTALL_HINT = "python3 -m pip install 'evozeus-session-signal-skill[nlp]'"


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
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
SENTENCE_SPLIT_RE = re.compile(r"[\n\r\t。！？!?；;，,、：:]+")
LEADING_MARKDOWN_RE = re.compile(r"^\s*(?:[-*+>]\s+|#{1,6}\s+|\d+[.)]\s+)")
PATH_OR_URL_RE = re.compile(r"(?:https?://|^//|/Users/|/var/folders|\.jsonl\b|[/\\][\w.-]+[/\\]?)", re.I)
FILE_TOKEN_RE = re.compile(
    r"^[\w./-]+\.(?:md|tsx?|jsx?|py|json|ya?ml|xml|png|jpe?g|svg|mjs|css|toml|lock)$",
    re.I,
)
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,4}|[A-Za-z][A-Za-z0-9_-]*")
HAS_TEXT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z]")
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


def event_factor_channel(event: Mapping[str, Any]) -> str:
    channel = str(event.get("factor_channel") or "")
    if channel:
        return channel
    role = str(event.get("role") or "")
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
    chat_role = str(event.get("chat_role") or "")
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


def canonical_text(event_or_text: Mapping[str, Any] | str) -> str:
    if isinstance(event_or_text, Mapping):
        if event_factor_channel(event_or_text) == "context":
            return ""
        value = str(event_or_text.get("factor_text") or event_or_text.get("text") or "")
    else:
        value = str(event_or_text)
    value = value.strip()
    if not value:
        return ""
    if len(value) > 5000:
        value = value[:5000]

    marker = REQUEST_MARKER_RE.search(value)
    if marker is not None:
        value = value[marker.end() :]
    elif value.lower().lstrip().startswith("# agents.md instructions"):
        return ""

    for pattern in DROP_BLOCK_PATTERNS:
        value = pattern.sub(" ", value)
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
    return True


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


def _fallback_tokens(value: str) -> list[str]:
    found = [token.lower() for token in TOKEN_RE.findall(value)]
    if len(found) > 1:
        return found
    compact = "".join(value.split()).lower()
    if re.search(r"[\u4e00-\u9fff]", compact):
        return [compact[index : index + 2] for index in range(max(1, len(compact) - 1))]
    return found
