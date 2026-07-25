from __future__ import annotations

from collections import Counter
import re
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import event_factor_channel, is_direct_user_input, signal_text


OFFICIAL_USER_INPUT_SENTIMENT_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.user-input-sentiment",
    "version": "v0.1.0",
    "title": "User input sentiment",
    "summary": "用轻量 NLP 判断用户输入里的满意度、不满风险、问题反馈和纠正请求，并保留事件证据。",
    "title_i18n": {
        "zh-CN": "用户输入情感",
        "en-US": "User input sentiment",
    },
    "summary_i18n": {
        "zh-CN": "用轻量 NLP 判断用户输入里的满意度、不满风险、问题反馈和纠正请求，并保留事件证据。",
        "en-US": "Classifies user input into dissatisfaction risk, problem reports, correction requests, neutral requests, and positive feedback.",
    },
    "compatibility": {"evozeus_protocol": ">=0.1.0"},
    "governance": {"owner": "evozeus-factor-maintainers"},
    "input_contract": {
        "event_model": "SessionEvent[]",
        "required_fields": ["events[].id", "events[].role", "events[].text"],
        "accepted_input_kinds": ["session", "project", "scan_record_set"],
        "target_types": ["session", "project", "scan_record_set"],
        "record_types": ["session_envelope"],
        "prior_result_policy": "not_required",
    },
    "evidence_contract": {
        "ref_format": "event:<event-id>",
        "privacy": "Official factors must use redacted user turns and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["tags", "scores", "statistics", "datasets", "presentations", "evidence_refs"],
        "dataset_semantic_types": ["user_sentiment", "frequency_distribution"],
        "presentation_components": ["builtin.bar_chart.v1", "builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "mixed user sentiment turns",
            "input": "factors/user-input-sentiment/session.json",
            "expected_status": "matched",
        }
    ],
}


class UserInputSentimentFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_USER_INPUT_SENTIMENT_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        records: list[Mapping[str, Any]] = []
        evidence_refs: list[Mapping[str, str]] = []

        has_prior_assistant_result = False
        for event in context.get("events", []):
            if not is_direct_user_input(event):
                if event_factor_channel(event) == "assistant_result":
                    has_prior_assistant_result = True
                continue
            text = signal_text(event)
            if not text:
                continue

            classified = _classify_sentiment_kind(text, is_follow_up=has_prior_assistant_result)
            sentiment_score = _sentiment_score(classified["label"])
            event_id = str(event.get("id", ""))
            records.append(
                {
                    "event_id": event_id,
                    "sentiment_kind": classified["label"],
                    "input_text": _preview_text(text),
                    "matched_excerpt": _matched_excerpt(text, classified["label"]),
                    "sentiment_score": sentiment_score,
                    "dissatisfaction_score": _dissatisfaction_score(classified["label"], sentiment_score),
                    "confidence": classified["confidence"],
                    "nlp_similarity_score": 0.0,
                    "nearest_example": classified["rule"],
                }
            )
            if event_id and classified["label"] != "neutral_request":
                evidence_refs.append({"ref_id": event_id, "kind": "user_turn"})

        if not records:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        distribution = Counter(str(record["sentiment_kind"]) for record in records)
        total = sum(distribution.values())
        distribution_records = [
            {
                    "sentiment_kind": sentiment,
                "count": int(count),
                "share": round(float(count) / float(total), 4),
            }
            for sentiment, count in sorted(distribution.items())
        ]
        average_score = sum(float(record["sentiment_score"]) for record in records) / float(len(records))
        signal_kinds = [str(record["sentiment_kind"]) for record in records if record["sentiment_kind"] != "neutral_request"]
        dominant_sentiment_kind = Counter(signal_kinds).most_common(1)[0][0] if signal_kinds else "neutral_request"
        status = "matched" if signal_kinds else "not_matched"

        return self.build_result(
            status=status,
            target_type="session",
            target_id=session_id,
            confidence=0.76,
            tags=[{"type": "user_sentiment", "value": dominant_sentiment_kind}],
            scores={"average_sentiment_score": average_score},
            statistics={
                "dominant_sentiment_kind": dominant_sentiment_kind,
                "user_turn_count": len(records),
                "dissatisfaction_turn_count": int(
                    distribution.get("dissatisfaction", 0)
                    + distribution.get("problem_report", 0)
                    + distribution.get("correction_request", 0)
                ),
            },
            datasets=[
                {
                    "id": "user_input_sentiment",
                    "semantic_type": "user_sentiment",
                    "shape": "record_set",
                    "primary_key": "event_id",
                    "records": records,
                    "schema": {
                        "event_id": "string",
                        "sentiment_kind": "string",
                        "input_text": "string",
                        "matched_excerpt": "string",
                        "sentiment_score": "number",
                        "dissatisfaction_score": "number",
                        "confidence": "number",
                    },
                },
                {
                    "id": "user_sentiment_distribution",
                    "semantic_type": "frequency_distribution",
                    "shape": "record_set",
                    "primary_key": "sentiment_kind",
                    "records": distribution_records,
                    "schema": {
                        "sentiment_kind": "string",
                        "count": "number",
                        "share": "number",
                    },
                },
            ],
            presentations=[
                {
                    "id": "user_sentiment_distribution_chart",
                    "title": "用户情绪分布",
                    "component_ref": "builtin.bar_chart.v1",
                    "data_ref": "user_sentiment_distribution",
                    "bindings": {"x": "sentiment_kind", "y": "count"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 75,
                },
                {
                    "id": "user_input_sentiment_table",
                    "title": "用户满意度/不满风险明细",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "user_input_sentiment",
                    "bindings": {"row_key": "event_id"},
                    "routes": ["drawer"],
                    "fallback": ["builtin.json.v1"],
                    "priority": 76,
                },
            ],
            evidence_refs=evidence_refs,
        )


def _classify_sentiment_kind(value: str, *, is_follow_up: bool = False) -> dict[str, Any]:
    normalized = value.lower()
    if META_REVIEW_REQUEST_RE.search(normalized):
        return {"label": "neutral_request", "confidence": 0.9, "rule": "meta review request"}
    if (
        _contains_any(normalized, NEGATED_PROBLEM_TERMS)
        or _contains_any(normalized, CORRECTION_TERMS)
        or CORRECTION_PATTERN_RE.search(normalized)
        or is_follow_up and FOLLOW_UP_CORRECTION_PATTERN_RE.search(normalized)
    ):
        return {"label": "correction_request", "confidence": 0.88, "rule": "explicit correction marker"}
    if _contains_any(normalized, PROBLEM_TERMS):
        return {"label": "problem_report", "confidence": 0.84, "rule": "explicit problem marker"}
    if _contains_any(normalized, DISSATISFACTION_TERMS) or DISSATISFACTION_PATTERN_RE.search(normalized):
        return {"label": "dissatisfaction", "confidence": 0.86, "rule": "explicit dissatisfaction marker"}
    if _contains_any(normalized, POSITIVE_TERMS):
        return {"label": "positive_feedback", "confidence": 0.82, "rule": "explicit positive marker"}
    return {"label": "neutral_request", "confidence": 0.7, "rule": "default neutral request"}


def _sentiment_score(label: str) -> float:
    return {
        "positive_feedback": 0.8,
        "neutral_request": 0.0,
        "problem_report": -0.45,
        "correction_request": -0.65,
        "dissatisfaction": -0.85,
    }.get(label, 0.0)


def _dissatisfaction_score(label: str, sentiment_score: float) -> float:
    if label in {"dissatisfaction", "problem_report", "correction_request"}:
        return round(min(1.0, abs(sentiment_score)), 4)
    return 0.0


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if term.isascii() and term.isalpha():
            if re.search(rf"\b{re.escape(term)}\b", value):
                return True
            continue
        if term in value:
            return True
    return False


def _matched_excerpt(value: str, label: str) -> str:
    terms = {
        "correction_request": CORRECTION_TERMS,
        "problem_report": PROBLEM_TERMS,
        "dissatisfaction": DISSATISFACTION_TERMS,
        "positive_feedback": POSITIVE_TERMS,
    }.get(label, ())
    for sentence in _split_sentences(value):
        lowered = sentence.lower()
        if any(term.lower() in lowered for term in terms):
            return _preview_text(sentence)
    return _preview_text(value)


def _split_sentences(value: str) -> list[str]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    current: list[str] = []
    for char in normalized:
        current.append(char)
        if char in "\n。！？!?；;":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts or [normalized.strip()]


def _preview_text(value: str, limit: int = 800) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}..."


CORRECTION_TERMS = (
    "但实际上",
    "实际上",
    "不对",
    "理解错",
    "方向不对",
    "改动太大",
    "不要这样",
    "不是这个",
    "不是我想要",
    "按我说",
    "重新按",
    "改成我说",
    "你看错",
    "搞错了",
    "没体现重点",
    "没有体现重点",
    "没看到爽点",
    "没看到价值",
    "不像真人写",
    "不是自然的中文",
    "ai味",
    "ai 味",
    "用词不精准",
    "只要结果",
    "不够强",
)
NEGATED_PROBLEM_TERMS = (
    "没有失败",
    "并没有失败",
    "没有报错",
    "并没有报错",
    "不是失败",
    "不是报错",
)
PROBLEM_TERMS = (
    "失败",
    "报错",
    "打不开",
    "没有返回",
    "没返回",
    "没生效",
    "不生效",
    "出错",
    "bug",
    "异常",
    "卡住",
    "崩溃",
    "无法运行",
    "不能运行",
)
DISSATISFACTION_TERMS = (
    "不满意",
    "不能接受",
    "体验很差",
    "又搞错",
    "完全不对",
    "太差",
    "乱掉",
    "不像在说人话",
    "不像说人话",
    "很蠢",
    "太蠢",
    "还不好",
)
POSITIVE_TERMS = (
    "谢谢",
    "效果很好",
    "这次可以",
    "验证通过",
    "很好",
    "works well",
    "lgtm",
)

CORRECTION_PATTERN_RE = re.compile(
    r"(?:还是|仍然|依旧)(?:没|没有|未)(?:体现|看到|看出|讲清|做到|解决|生效|打开)"
    r"|(?:太|过于)(?:长|短|泛|复杂|啰嗦|技术化)"
    r"|(?:有点|比较)(?:泛|长|短|乱|复杂|薄|简单)"
    r"|(?:hook|钩子|机制|逻辑|方向)[^。！？!?]{0,20}(?:搞错|错了|不对)"
    r"|不要[^。！？!?]{0,30}(?:只要|就好|就行|即可)"
    r"|还要再(?:详细|具体|精简|短|长)"
    r"|(?:还是|还)(?:不够|差一点)"
    r"|要换位思考"
    r"|没有思路打开"
)

FOLLOW_UP_CORRECTION_PATTERN_RE = re.compile(
    r"(?:先)?帮我把[^。！？!?]{1,40}(?:搞明白|改好|完善|讲清楚)"
    r"|学一下(?:人家|这个|它)"
    r"|不要(?:做决策|那么多|一大段|类codex)"
)

DISSATISFACTION_PATTERN_RE = re.compile(
    r"(?:还是|仍然|依旧)?(?:都)?看不懂"
    r"|(?:还是|仍然|依旧|方向)?[^。！？!?]{0,8}(?:很蠢|太蠢|很普通)"
    r"|(?:^|[，,。])不好(?:[，,。！？!?]|$)"
    r"|思路打开(?:行吗|一点)"
)

META_REVIEW_REQUEST_RE = re.compile(
    r"(?:review|检查|审查|评审|分析)[^。！？!?\n]{0,30}(?:prompt|提示词|文案)[^。！？!?\n]{0,20}(?:是否|有没有|看)"
)
