from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import canonical_text, channel_events, classify_by_examples


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

        for event in channel_events(context.get("events", []), {"user_input"}):
            text = canonical_text(event)
            if not text:
                continue

            classified = _classify_sentiment_kind(text)
            sentiment_score = _sentiment_score(classified.label, classified.snownlp_score)
            event_id = str(event.get("id", ""))
            records.append(
                {
                    "event_id": event_id,
                    "sentiment_kind": classified.label,
                    "sentiment_score": sentiment_score,
                    "dissatisfaction_score": _dissatisfaction_score(classified.label, sentiment_score),
                    "confidence": classified.confidence,
                    "nlp_similarity_score": classified.score,
                    "nearest_example": classified.nearest_example[:80],
                }
            )
            if event_id:
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
        dominant_sentiment_kind = distribution.most_common(1)[0][0]

        return self.build_result(
            status="matched",
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


SENTIMENT_EXAMPLES = {
    "dissatisfaction": [
        "这完全不对，我很不满意",
        "你又搞错了，结果不能接受",
        "还是没生效，怎么回事",
        "这次体验很差",
    ],
    "problem_report": [
        "运行失败了，测试还在报错",
        "页面打不开，日志里有异常",
        "工具没有返回结果",
        "部署失败，出现错误",
    ],
    "correction_request": [
        "不对，改动太大了，排版不要大变化",
        "这个方向不对，重新按我的要求改",
        "不要这样实现，按原来的结构调整",
        "你理解错了，改成我说的方案",
    ],
    "neutral_request": [
        "继续看一下测试结果",
        "帮我检查这个文件",
        "统计一下所有 session",
        "把这个 factor 修改一下",
    ],
    "positive_feedback": [
        "谢谢，效果很好",
        "这次可以，验证通过了",
        "很好，继续保持这个方向",
        "thanks, this works well",
    ],
}


def _classify_sentiment_kind(value: str):
    return classify_by_examples(value, SENTIMENT_EXAMPLES)


def _sentiment_score(label: str, snownlp_score: float) -> float:
    base = {
        "positive_feedback": 0.8,
        "neutral_request": 0.0,
        "problem_report": -0.45,
        "correction_request": -0.65,
        "dissatisfaction": -0.85,
    }.get(label, 0.0)
    snow_adjustment = (snownlp_score - 0.5) * 0.3
    return round(max(-1.0, min(1.0, base + snow_adjustment)), 4)


def _dissatisfaction_score(label: str, sentiment_score: float) -> float:
    if label in {"dissatisfaction", "problem_report", "correction_request"}:
        return round(min(1.0, abs(sentiment_score)), 4)
    return 0.0
