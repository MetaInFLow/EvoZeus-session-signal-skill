from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


POSITIVE_TERMS = (
    "谢谢",
    "感谢",
    "不错",
    "很好",
    "可以",
    "满意",
    "喜欢",
    "赞",
    "thanks",
    "great",
    "good",
    "nice",
    "love",
    "works",
)
NEGATIVE_TERMS = (
    "生气",
    "烦",
    "糟糕",
    "不行",
    "失败",
    "讨厌",
    "失望",
    "太慢",
    "报错",
    "不满意",
    "bad",
    "terrible",
    "angry",
    "frustrated",
    "fail",
    "broken",
    "wrong",
)


OFFICIAL_USER_INPUT_SENTIMENT_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.user-input-sentiment",
    "version": "v0.1.0",
    "title": "User input sentiment",
    "summary": "判断用户在会话里表达的是正向、负向还是中性情绪，并保留对应用户消息作为证据。",
    "title_i18n": {
        "zh-CN": "用户输入情感",
        "en-US": "User input sentiment",
    },
    "summary_i18n": {
        "zh-CN": "判断用户在会话里表达的是正向、负向还是中性情绪，并保留对应用户消息作为证据。",
        "en-US": "Classifies user messages as positive, negative, or neutral and keeps message evidence.",
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

        for event in context.get("events", []):
            if event.get("role") != "user":
                continue

            sentiment, sentiment_score, confidence, matched_terms = _classify_sentiment(str(event.get("text", "")))
            event_id = str(event.get("id", ""))
            records.append(
                {
                    "event_id": event_id,
                    "sentiment": sentiment,
                    "sentiment_score": sentiment_score,
                    "confidence": confidence,
                    "matched_terms": ", ".join(matched_terms),
                }
            )
            if event_id:
                evidence_refs.append({"ref_id": event_id, "kind": "user_turn"})

        if not records:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        distribution = Counter(str(record["sentiment"]) for record in records)
        total = sum(distribution.values())
        distribution_records = [
            {
                "sentiment": sentiment,
                "count": int(count),
                "share": round(float(count) / float(total), 4),
            }
            for sentiment, count in sorted(distribution.items())
        ]
        average_score = sum(float(record["sentiment_score"]) for record in records) / float(len(records))
        overall_sentiment = _overall_sentiment(average_score)

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.68,
            tags=[{"type": "user_sentiment", "value": overall_sentiment}],
            scores={"average_sentiment_score": average_score},
            statistics={"overall_sentiment": overall_sentiment, "user_turn_count": len(records)},
            datasets=[
                {
                    "id": "user_input_sentiment",
                    "semantic_type": "user_sentiment",
                    "shape": "record_set",
                    "primary_key": "event_id",
                    "records": records,
                    "schema": {
                        "event_id": "string",
                        "sentiment": "string",
                        "sentiment_score": "number",
                        "confidence": "number",
                    },
                },
                {
                    "id": "user_sentiment_distribution",
                    "semantic_type": "frequency_distribution",
                    "shape": "record_set",
                    "primary_key": "sentiment",
                    "records": distribution_records,
                    "schema": {
                        "sentiment": "string",
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
                    "bindings": {"x": "sentiment", "y": "count"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 75,
                },
                {
                    "id": "user_input_sentiment_table",
                    "title": "用户情绪明细",
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


def _classify_sentiment(value: str) -> tuple[str, float, float, list[str]]:
    normalized = value.lower()
    positive_matches = [term for term in POSITIVE_TERMS if term.lower() in normalized]
    negative_matches = [term for term in NEGATIVE_TERMS if term.lower() in normalized]
    raw_score = len(positive_matches) - len(negative_matches)

    if raw_score > 0:
        sentiment = "positive"
    elif raw_score < 0:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    sentiment_score = max(-1.0, min(1.0, raw_score / 2.0))
    confidence = 0.5 if raw_score == 0 else min(0.9, 0.65 + 0.1 * abs(raw_score))
    return sentiment, sentiment_score, confidence, positive_matches + negative_matches


def _overall_sentiment(score: float) -> str:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"
