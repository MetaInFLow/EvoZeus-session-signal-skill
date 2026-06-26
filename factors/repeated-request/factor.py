from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import canonical_text, event_factor_channel

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
except ImportError:  # pragma: no cover - dependency is validated by shared NLP helper.
    rapidfuzz_fuzz = None


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
        prior_requests: list[tuple[Mapping[str, Any], str]] = []
        matches: list[tuple[str, Mapping[str, Any], Mapping[str, Any], float]] = []

        for event in context.get("events", []):
            if event_factor_channel(event) == "user_input":
                text = canonical_text(event)
                signature = _request_signature(text)
                if not signature:
                    continue
                prior_match = _best_prior_match(signature, prior_requests)
                if prior_match is not None:
                    prior_event, score = prior_match
                    chain_id = f"repeat_chain_{len(matches) + 1}"
                    matches.append((chain_id, prior_event, event, score))
                prior_requests.append((event, signature))
                prior_requests = prior_requests[-12:]
            elif _looks_resolved(str(event.get("text", "")), str(event.get("role", ""))):
                prior_requests.clear()

        if not matches:
            return self.build_result(status="not_matched", target_type="session", target_id=str(context.get("session_id", "")))

        records = [
            {
                "chain_id": chain_id,
                "first_event_id": str(first_event.get("id", "")),
                "repeat_event_id": str(repeat_event.get("id", "")),
                "event_id": str(repeat_event.get("id", "")),
                "role": "user",
                "similarity_score": round(score, 4),
                "request_signature": _request_signature(canonical_text(repeat_event))[:120],
                "signal": "user repeated a previously unresolved request",
            }
            for chain_id, first_event, repeat_event, score in matches
        ]

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=str(context.get("session_id", "")),
            confidence=0.72,
            tags=[{"type": "loop", "value": "repeated-request"}],
            scores={"repeated_request_count": float(len(matches))},
            datasets=[
                {
                    "id": "repeated_request_events",
                    "semantic_type": "evidence_record_set",
                    "shape": "record_set",
                    "primary_key": "event_id",
                    "records": records,
                    "schema": {
                        "chain_id": "string",
                        "first_event_id": "string",
                        "repeat_event_id": "string",
                        "event_id": "string",
                        "role": "string",
                        "similarity_score": "number",
                        "request_signature": "string",
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
            evidence_refs=[
                {"ref_id": str(repeat_event.get("id", "")), "kind": "user_turn"}
                for _, _, repeat_event, _ in matches
                if repeat_event.get("id")
            ],
        )


STOP_TOKENS = {
    "一下",
    "这些",
    "这个",
    "那个",
    "感觉",
    "看看",
    "还是",
    "again",
    "same",
    "request",
    "继续",
    "开始",
    "ok",
    "好的",
}
RESOLVED_TERMS = ("完成", "已完成", "测试通过", "done", "completed", "fixed", "resolved", "task complete")
REQUEST_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]*")


def _request_signature(value: str) -> str:
    normalized = value.lower().replace("factors", "factor")
    normalized = normalized.replace("review 一下", "review一下").replace("review一下", "review")
    normalized = normalized[:500]
    token_list = []
    for token in REQUEST_TOKEN_RE.findall(normalized):
        token = token.lower()
        if token not in STOP_TOKENS:
            token_list.append(token)
        if len(token_list) >= 32:
            break
    if len(token_list) < 2:
        return ""
    signature = " ".join(token_list)
    if len(signature.replace(" ", "")) < 4:
        return ""
    return signature[:240]


def _best_prior_match(
    signature: str,
    prior_requests: list[tuple[Mapping[str, Any], str]],
) -> tuple[Mapping[str, Any], float] | None:
    best_event: Mapping[str, Any] | None = None
    best_score = 0.0
    for event, previous_signature in prior_requests:
        score = _signature_similarity(signature, previous_signature)
        if score > best_score:
            best_event = event
            best_score = score
    if best_event is not None and best_score >= 0.72:
        return best_event, best_score
    return None


def _signature_similarity(current: str, previous: str) -> float:
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(current[:240], previous[:240])) / 100.0
    return SequenceMatcher(None, current, previous).ratio()


def _looks_resolved(value: str, role: str) -> bool:
    if role == "task_complete":
        return True
    normalized = value.lower()
    return any(term.lower() in normalized for term in RESOLVED_TERMS)
