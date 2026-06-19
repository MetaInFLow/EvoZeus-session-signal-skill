from __future__ import annotations

from typing import Any, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


OFFICIAL_REPEATED_REQUEST_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.repeated-request",
    "version": "v0.1.0",
    "title": "Repeated request",
    "summary": "识别用户是否重复提出同一个还没有解决的请求，并列出对应消息证据。",
    "title_i18n": {
        "zh-CN": "重复请求识别",
        "en-US": "Repeated request",
    },
    "summary_i18n": {
        "zh-CN": "识别用户是否重复提出同一个还没有解决的请求，并列出对应消息证据。",
        "en-US": "Detects whether the user repeated an unresolved request and returns message evidence.",
    },
    "compatibility": {
        "evozeus_protocol": ">=0.1.0",
    },
    "governance": {
        "owner": "evozeus-factor-maintainers",
    },
    "input_contract": {
        "event_model": "SessionEvent[]",
        "required_fields": ["events[].id", "events[].role", "events[].text"],
        "accepted_input_kinds": ["session"],
        "target_types": ["session"],
        "record_types": ["session_envelope"],
        "prior_result_policy": "not_required",
    },
    "evidence_contract": {
        "ref_format": "event:<event-id>",
        "privacy": "Official factors must use redacted events and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["tags", "scores", "datasets", "presentations", "verdict_signals", "evidence_refs"],
        "dataset_semantic_types": ["evidence_record_set"],
        "presentation_components": ["builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "user asks again",
            "input": "factors/repeated-request/session.json",
            "expected_status": "matched",
        }
    ],
}


class RepeatedRequestFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_REPEATED_REQUEST_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        matched_event = next(
            (
                event
                for event in context.get("events", [])
                if event.get("role") == "user"
                and any(token in str(event.get("text", "")).lower() for token in ["again", "same request"])
            ),
            None,
        )

        if matched_event is None:
            return self.build_result(status="not_matched", target_type="session", target_id=str(context.get("session_id", "")))

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=str(context.get("session_id", "")),
            confidence=0.72,
            tags=[{"type": "loop", "value": "repeated-request"}],
            scores={"repeated_request_count": 1.0},
            datasets=[
                {
                    "id": "repeated_request_events",
                    "semantic_type": "evidence_record_set",
                    "shape": "record_set",
                    "primary_key": "event_id",
                    "records": [
                        {
                            "event_id": str(matched_event["id"]),
                            "role": str(matched_event.get("role", "")),
                            "signal": "user repeated a previously unresolved request",
                        }
                    ],
                    "schema": {
                        "event_id": "string",
                        "role": "string",
                        "signal": "string",
                    },
                }
            ],
            presentations=[
                {
                    "id": "repeated_request_table",
                    "title": "Repeated request events",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "repeated_request_events",
                    "bindings": {"row_key": "event_id"},
                    "routes": ["drawer"],
                    "fallback": ["builtin.json.v1"],
                }
            ],
            verdict_signals=["user repeated a previously unresolved request"],
            evidence_refs=[{"ref_id": str(matched_event["id"]), "kind": "user_turn"}],
        )
