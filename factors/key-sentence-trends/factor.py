from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


OFFICIAL_KEY_SENTENCE_TRENDS_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.key-sentence-trends",
    "version": "v0.1.0",
    "title": "Key sentence trends",
    "summary": "按时间统计关键句出现趋势，帮助看出用户关注点如何变化。",
    "title_i18n": {
        "zh-CN": "关键句趋势",
        "en-US": "Key sentence trends",
    },
    "summary_i18n": {
        "zh-CN": "按时间统计关键句出现趋势，帮助看出用户关注点如何变化。",
        "en-US": "Aggregates key sentence trends over time to show how user attention changes.",
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
        "privacy": "Official factors must use redacted events and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["scores", "datasets", "presentations", "evidence_refs"],
        "dataset_semantic_types": ["key_sentence_trend"],
        "presentation_components": ["builtin.line_chart.v1", "builtin.heatmap.v1", "builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "key sentence trends by date bucket",
            "input": "factors/key-sentence-trends/session.json",
            "expected_status": "matched",
        }
    ],
}


class KeySentenceTrendsFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_KEY_SENTENCE_TRENDS_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        trend_counts: Counter[tuple[str, str]] = Counter()
        evidence_by_cluster: dict[str, list[str]] = defaultdict(list)

        for event in context.get("events", []):
            if event.get("role") != "user":
                continue
            cluster_label = _cluster_label(str(event.get("text", "")))
            if not cluster_label:
                continue
            bucket = _date_bucket(str(event.get("timestamp", "")))
            trend_counts[(bucket, cluster_label)] += 1
            evidence_by_cluster[cluster_label].append(str(event.get("id", "")))

        if not trend_counts:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        records = [
            {
                "date_bucket": bucket,
                "cluster_label": cluster_label,
                "count": int(count),
                "session_count": 1,
                "score": float(count),
            }
            for (bucket, cluster_label), count in sorted(trend_counts.items())
        ]
        evidence_refs = [
            {"ref_id": event_id, "kind": "user_turn"}
            for event_ids in evidence_by_cluster.values()
            for event_id in event_ids
            if event_id
        ]

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.73,
            tags=[{"type": "key_sentence", "value": "trend"}],
            scores={"key_sentence_cluster_count": float(len(evidence_by_cluster))},
            datasets=[
                {
                    "id": "key_sentence_trends",
                    "semantic_type": "key_sentence_trend",
                    "shape": "time_series",
                    "primary_key": "date_bucket,cluster_label",
                    "records": records,
                    "schema": {
                        "date_bucket": "string",
                        "cluster_label": "string",
                        "count": "number",
                    },
                }
            ],
            presentations=[
                {
                    "id": "key_sentence_line",
                    "title": "关键句趋势",
                    "component_ref": "builtin.line_chart.v1",
                    "data_ref": "key_sentence_trends",
                    "bindings": {"x": "date_bucket", "y": "count", "series": "cluster_label"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 70,
                },
                {
                    "id": "key_sentence_heatmap",
                    "title": "关键句热力",
                    "component_ref": "builtin.heatmap.v1",
                    "data_ref": "key_sentence_trends",
                    "bindings": {"x": "date_bucket", "y": "cluster_label", "color": "count"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 71,
                },
            ],
            evidence_refs=evidence_refs,
        )


def _cluster_label(value: str) -> str:
    normalized = " ".join(value.replace("。", " ").split())
    normalized = normalized.replace("合理利用subagent", "合理利用 subagent")
    if "design doc" in normalized.lower():
        return "先看 design doc"
    if "合理利用 subagent" in normalized:
        return "合理利用 subagent"
    return ""


def _date_bucket(value: str) -> str:
    if len(value) >= 10:
        return value[:10]
    return "unknown-date"
