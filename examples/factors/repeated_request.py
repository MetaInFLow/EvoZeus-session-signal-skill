from __future__ import annotations

from typing import Any, Mapping

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


OFFICIAL_REPEATED_REQUEST_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.example.repeated-request",
    "version": "v0.1.0",
    "title": "Repeated request",
    "summary": "Canonical example for detecting a repeated user request with explicit event evidence.",
    "compatibility": {
        "evozeus_protocol": ">=0.1.0",
    },
    "governance": {
        "owner": "evozeus-factor-maintainers",
    },
    "input_contract": {
        "event_model": "SessionEvent[]",
        "required_fields": ["events[].id", "events[].role", "events[].text"],
    },
    "evidence_contract": {
        "ref_format": "event:<event-id>",
        "privacy": "Canonical examples must use redacted events and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "error"],
        "fields": ["tags", "verdict_signals", "evidence_refs"],
    },
    "examples": [
        {
            "name": "user asks again",
            "input": "examples/sessions/repeated-request.json",
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
            return self.build_result(status="not_matched")

        return self.build_result(
            status="matched",
            confidence=0.72,
            tags=["loop:repeated-request"],
            verdict_signals=["user repeated a previously unresolved request"],
            evidence_refs=[f"event:{matched_event['id']}"],
        )
