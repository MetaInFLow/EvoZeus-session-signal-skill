from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import direct_user_events, semantic_phrase_candidates


OFFICIAL_SEMANTIC_PHRASE_CLUSTERS_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.semantic-phrase-clusters",
    "version": "v0.1.0",
    "title": "Semantic phrase clusters",
    "summary": "Groups semantically equivalent direct-user phrases into stable intent clusters.",
    "title_i18n": {"zh-CN": "语义短句聚类", "en-US": "Semantic phrase clusters"},
    "summary_i18n": {
        "zh-CN": "把用户本人表达的同义短句归并为稳定意图簇，并保留变体、计数和事件证据。",
        "en-US": "Groups semantically equivalent direct-user phrases into stable intent clusters with variants, counts, and evidence.",
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
        "privacy": "Official factors must use redacted direct-user events and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["tags", "scores", "statistics", "datasets", "presentations", "evidence_refs"],
        "dataset_semantic_types": ["semantic_phrase_cluster_set"],
        "presentation_components": ["builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "run project phrase variants",
            "input": "factors/semantic-phrase-clusters/session.json",
            "expected_status": "matched",
        }
    ],
}


class SemanticPhraseClustersFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_SEMANTIC_PHRASE_CLUSTERS_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        variants_by_cluster: dict[str, set[str]] = defaultdict(set)
        evidence_by_cluster: dict[str, list[str]] = defaultdict(list)
        label_by_cluster: dict[str, str] = {}

        for event in direct_user_events(context.get("events", [])):
            event_id = str(event.get("id") or "")
            seen_clusters: set[str] = set()
            for candidate in semantic_phrase_candidates(event):
                variants_by_cluster[candidate.cluster_id].add(candidate.text)
                label_by_cluster[candidate.cluster_id] = candidate.label
                if event_id and candidate.cluster_id not in seen_clusters:
                    evidence_by_cluster[candidate.cluster_id].append(event_id)
                    seen_clusters.add(candidate.cluster_id)

        records = []
        for cluster_id in sorted(variants_by_cluster):
            event_ids = list(dict.fromkeys(evidence_by_cluster[cluster_id]))
            if len(event_ids) < 2:
                continue
            variants = sorted(variants_by_cluster[cluster_id])
            records.append(
                {
                    "cluster_id": cluster_id,
                    "label": label_by_cluster[cluster_id],
                    "representative_phrase": variants[0],
                    "variants": variants,
                    "turn_count": len(event_ids),
                    "session_count": 1,
                    "variant_count": len(variants),
                    "sample_event_ids": event_ids[:5],
                }
            )

        if not records:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        evidence_refs = [
            {"ref_id": event_id, "kind": "user_turn"}
            for record in records
            for event_id in evidence_by_cluster[str(record["cluster_id"])]
        ]
        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.82,
            tags=[{"type": "semantic_phrase", "value": "clustered"}],
            scores={"semantic_phrase_cluster_count": float(len(records))},
            statistics={"cluster_count": len(records)},
            datasets=[
                {
                    "id": "semantic_phrase_clusters",
                    "semantic_type": "semantic_phrase_cluster_set",
                    "shape": "record_set",
                    "primary_key": "cluster_id",
                    "records": records,
                    "schema": {
                        "cluster_id": "string",
                        "label": "string",
                        "representative_phrase": "string",
                        "variants": "string[]",
                        "turn_count": "number",
                        "session_count": "number",
                        "variant_count": "number",
                    },
                }
            ],
            presentations=[
                {
                    "id": "semantic_phrase_cluster_table",
                    "title": "语义短句聚类",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "semantic_phrase_clusters",
                    "bindings": {"row_key": "cluster_id"},
                    "routes": ["dashboard", "drawer"],
                    "fallback": ["builtin.json.v1"],
                    "priority": 80,
                }
            ],
            evidence_refs=evidence_refs,
        )
