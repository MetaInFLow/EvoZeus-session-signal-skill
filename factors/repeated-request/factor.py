from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import canonical_text, event_factor_channel, is_direct_user_input, semantic_request_signature, signal_text

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
        prior_requests: list[tuple[int, Mapping[str, Any], str, str]] = []
        matches: list[tuple[str, Mapping[str, Any], Mapping[str, Any], float, str, str]] = []
        previous_user_text = ""
        previous_user_line = -1

        last_assistant_index = -1
        for index, event in enumerate(context.get("events", [])):
            if is_direct_user_input(event):
                text = signal_text(event)
                if not text:
                    continue
                current_line = _source_line(event)
                if text == previous_user_text and 0 <= previous_user_line and current_line <= previous_user_line + 2:
                    continue
                previous_user_text = text
                previous_user_line = current_line
                signature = _request_signature(text)
                if not signature:
                    continue
                prior_match = _latest_exact_resend(text, prior_requests, current_line)
                if prior_match is None and _looks_like_reask(text, signature):
                    prior_match = _best_prior_match(signature, text, prior_requests, last_assistant_index)
                if prior_match is None and _is_anaphoric_reask(text):
                    prior_match = _latest_prior_before_assistant(prior_requests, last_assistant_index)
                if prior_match is not None:
                    prior_event, score, prior_text = prior_match
                    chain_id = f"repeat_chain_{len(matches) + 1}"
                    matches.append((chain_id, prior_event, event, score, prior_text, text))
                prior_requests.append((index, event, signature, text))
                prior_requests = prior_requests[-24:]
            elif event_factor_channel(event) == "assistant_result":
                last_assistant_index = index

        if not matches:
            return self.build_result(status="not_matched", target_type="session", target_id=str(context.get("session_id", "")))

        records = [
            {
                "chain_id": chain_id,
                "first_event_id": str(first_event.get("id", "")),
                "repeat_event_id": str(repeat_event.get("id", "")),
                "event_id": str(repeat_event.get("id", "")),
                "role": "user",
                "first_input_text": _preview_text(first_text),
                "repeat_input_text": _preview_text(repeat_text),
                "similarity_score": round(score, 4),
                "request_signature": _request_signature(canonical_text(repeat_event))[:120],
                "signal": "user repeated a previously unresolved request",
            }
            for chain_id, first_event, repeat_event, score, first_text, repeat_text in matches
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
                        "first_input_text": "string",
                        "repeat_input_text": "string",
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
                for _, _, repeat_event, _, _, _ in matches
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
    semantic_signature = semantic_request_signature(value)
    if semantic_signature:
        return semantic_signature
    normalized = value.lower().replace("factors", "factor")
    if "data:image" in normalized or "image_url" in normalized or "base64" in normalized:
        return ""
    normalized = normalized.replace("review 一下", "review一下").replace("review一下", "review")
    normalized = normalized[:500]
    token_list = []
    for token in REQUEST_TOKEN_RE.findall(normalized):
        token = token.lower()
        if token not in STOP_TOKENS:
            token_list.append(token)
        if len(token_list) >= 32:
            break
    if not token_list:
        return ""
    signature = " ".join(token_list)
    if len(signature.replace(" ", "")) < 4:
        return ""
    return signature[:240]


def _best_prior_match(
    signature: str,
    current_text: str,
    prior_requests: list[tuple[int, Mapping[str, Any], str, str]],
    last_assistant_index: int,
) -> tuple[Mapping[str, Any], float, str] | None:
    if signature == "intent.run_project":
        for event_index, event, previous_signature, previous_text in prior_requests:
            if event_index < last_assistant_index and previous_signature == signature:
                return event, 1.0, previous_text
    best_event: Mapping[str, Any] | None = None
    best_score = 0.0
    best_text = ""
    for event_index, event, previous_signature, previous_text in prior_requests:
        if last_assistant_index <= event_index:
            continue
        score = _signature_similarity(signature, previous_signature)
        if signature.startswith("intent.") and signature == previous_signature:
            score = 0.8 + 0.2 * _signature_similarity(current_text, previous_text)
        if score > best_score:
            best_event = event
            best_score = score
            best_text = previous_text
    if best_event is not None and best_score >= 0.72:
        return best_event, best_score, best_text
    return None


def _latest_exact_resend(
    text: str,
    prior_requests: list[tuple[int, Mapping[str, Any], str, str]],
    current_line: int,
) -> tuple[Mapping[str, Any], float, str] | None:
    if current_line < 0:
        return None
    for _, event, _, previous_text in reversed(prior_requests):
        previous_line = _source_line(event)
        if previous_text == text and previous_line >= 0 and current_line > previous_line + 2:
            return event, 1.0, previous_text
    return None


def _latest_prior_before_assistant(
    prior_requests: list[tuple[int, Mapping[str, Any], str, str]],
    last_assistant_index: int,
) -> tuple[Mapping[str, Any], float, str] | None:
    for event_index, event, _, previous_text in reversed(prior_requests):
        if event_index < last_assistant_index:
            return event, 0.8, previous_text
    return None


def _looks_like_reask(value: str, signature: str) -> bool:
    normalized = value.lower()
    if "我希望" in normalized and "为什么" in normalized and "不同" in normalized:
        return False
    return bool(
        signature == "intent.run_project"
        or re.search(r"(?:还是|仍然|依旧)[^。！？!?]{0,30}(?:没|没有|不|看不懂)", normalized)
        or re.search(r"(?:继续|重新|再来|再讲|再说|再解释|再检查|再\s*review)", normalized)
        or "告诉我" in normalized
        or "again" in normalized
    )


def _is_anaphoric_reask(value: str) -> bool:
    normalized = value.lower()
    return bool(re.search(r"(?:same|同样|同一个).{0,12}(?:request|请求).{0,12}(?:again|再)", normalized))


def _signature_similarity(current: str, previous: str) -> float:
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(current[:240], previous[:240])) / 100.0
    return SequenceMatcher(None, current, previous).ratio()


def _source_line(event: Mapping[str, Any]) -> int:
    try:
        direct_line = int(event.get("source_line") or 0)
    except (TypeError, ValueError):
        direct_line = 0
    if direct_line > 0:
        return direct_line
    locator = event.get("event_locator_json")
    if isinstance(locator, Mapping):
        payload = locator.get("payload")
        if isinstance(payload, Mapping):
            try:
                return int(payload.get("line_start") or 0)
            except (TypeError, ValueError):
                return -1
    event_id = str(event.get("id") or "")
    if "#L" in event_id:
        try:
            return int(event_id.rsplit("#L", 1)[1])
        except ValueError:
            return -1
    return -1


def _preview_text(value: str, limit: int = 800) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}..."
