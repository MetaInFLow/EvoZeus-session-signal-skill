from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


OFFICIAL_USAGE_SENTENCE_CLOUD_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.usage-sentence-cloud",
    "version": "v0.1.0",
    "title": "Usage sentence cloud",
    "summary": "找出用户会话里反复出现的常用表达，并用词云展示高频句子。",
    "title_i18n": {
        "zh-CN": "高频使用句云",
        "en-US": "Usage sentence cloud",
    },
    "summary_i18n": {
        "zh-CN": "找出用户会话里反复出现的常用表达，并用词云展示高频句子。",
        "en-US": "Finds repeated user expressions in sessions and presents frequent sentences as a word cloud.",
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
        "dataset_semantic_types": ["high_frequency_phrase_set"],
        "presentation_components": ["builtin.word_cloud.v1", "builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "usage sentence repeats across user turns",
            "input": "factors/usage-sentence-cloud/session.json",
            "expected_status": "matched",
        }
    ],
}


class UsageSentenceCloudFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_USAGE_SENTENCE_CLOUD_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        counter: Counter[str] = Counter()
        evidence_by_sentence: dict[str, list[str]] = defaultdict(list)
        session_id = str(context.get("session_id", ""))

        for event in context.get("events", []):
            if event.get("role") != "user":
                continue
            sentence = _normalize_sentence(str(event.get("text", "")))
            if not sentence:
                continue
            counter[sentence] += 1
            evidence_by_sentence[sentence].append(str(event.get("id", "")))

        if not counter:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        records = []
        for sentence, count in counter.most_common(20):
            score = float(count + 0.1)
            records.append(
                {
                    "sentence_id": _stable_sentence_id(sentence),
                    "display_sentence": sentence,
                    "text": sentence,
                    "value": score,
                    "weight": score,
                    "count": int(count),
                    "raw_count": int(count),
                    "session_count": 1,
                    "category": "工作流句" if "subagent" in sentence else "使用句",
                    "sample_session_ids": [session_id],
                }
            )

        top_sentence = str(records[0]["display_sentence"])
        evidence_refs = [{"ref_id": event_id, "kind": "user_turn"} for event_id in evidence_by_sentence[top_sentence] if event_id]

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.74,
            tags=[{"type": "usage_sentence", "value": "high_frequency"}],
            scores={"usage_sentence_count": float(len(records))},
            datasets=[
                {
                    "id": "usage_sentence_cloud",
                    "semantic_type": "high_frequency_phrase_set",
                    "shape": "record_set",
                    "primary_key": "sentence_id",
                    "records": records,
                    "schema": {
                        "sentence_id": "string",
                        "text": "string",
                        "value": "number",
                        "category": "string",
                    },
                }
            ],
            presentations=[
                {
                    "id": "usage_sentence_word_cloud",
                    "title": "高频使用句云",
                    "component_ref": "builtin.word_cloud.v1",
                    "data_ref": "usage_sentence_cloud",
                    "bindings": {"word": "text", "weight": "value", "color": "category"},
                    "props": {"height": 420},
                    "routes": ["dashboard", "drawer"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 80,
                }
            ],
            evidence_refs=evidence_refs,
        )


def _normalize_sentence(value: str) -> str:
    value = " ".join(value.replace("。", " ").split())
    value = value.replace("要合理利用 subagent", "合理利用 subagent")
    value = value.replace("合理利用subagent", "合理利用 subagent")
    if "合理利用 subagent" in value:
        return "合理利用 subagent"
    if "拉起来看下" in value:
        return "拉起来看下"
    return value


def _stable_sentence_id(sentence: str) -> str:
    digest = hashlib.sha256(sentence.encode("utf-8")).hexdigest()[:12]
    return f"usage_sentence_{digest}"
