from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from .factor import OfficialFactor, OfficialFactorResult
from .resources import factors_root


EXPECTED_GOLDEN_FACTOR_IDS = {
    "official.key-sentence-trends",
    "official.repeated-request",
    "official.semantic-phrase-clusters",
    "official.session-resource-usage",
    "official.task-completion",
    "official.tool-failure-frequency",
    "official.user-input-sentiment",
}


@dataclass(frozen=True)
class GoldenSession:
    golden_id: str
    source_path: Path
    display_title: str
    source_note: str
    review_note: str
    review_status: str
    provenance: Mapping[str, Any]
    session: Mapping[str, Any]
    expected_factor_results: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class FactorScore:
    factor_id: str
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float


def load_golden_sessions(session_dir: Path) -> list[GoldenSession]:
    if not session_dir.is_dir():
        raise FileNotFoundError(f"golden session directory not found: {session_dir}")

    sessions = [_load_golden_session(path) for path in sorted(session_dir.glob("*.json"))]
    if not sessions:
        raise ValueError(f"no golden sessions found in {session_dir}")
    return sessions


def compare_answers(expected: Any, actual: Any, *, path: str = "") -> list[str]:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        differences: list[str] = []
        for key in expected:
            child_path = f"{path}.{key}" if path else str(key)
            if key not in actual:
                differences.append(f"{child_path}: expected={expected[key]!r} actual=<missing>")
                continue
            differences.extend(compare_answers(expected[key], actual[key], path=child_path))
        for key in actual:
            if key in expected:
                continue
            child_path = f"{path}.{key}" if path else str(key)
            differences.append(f"{child_path}: expected=<missing> actual={actual[key]!r}")
        return differences

    if isinstance(expected, list) and isinstance(actual, list):
        expected_sorted = sorted(expected, key=_canonical_json)
        actual_sorted = sorted(actual, key=_canonical_json)
        return [] if expected_sorted == actual_sorted else [f"{path}: expected={expected_sorted!r} actual={actual_sorted!r}"]

    if expected != actual:
        return [f"{path}: expected={expected!r} actual={actual!r}"]
    return []


def evaluate_golden_sessions(session_dir: Path) -> list[str]:
    failures: list[str] = []
    for golden in load_golden_sessions(session_dir):
        actual_answers = generate_factor_answers(golden.session)
        for factor_id in sorted(EXPECTED_GOLDEN_FACTOR_IDS):
            actual = actual_answers[factor_id]
            expected = golden.expected_factor_results[factor_id]
            for difference in compare_answers(expected, actual):
                failures.append(f"{golden.golden_id} {factor_id} {difference}")
    return failures


def score_golden_sessions(session_dir: Path) -> list[FactorScore]:
    answer_pairs: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {
        factor_id: [] for factor_id in EXPECTED_GOLDEN_FACTOR_IDS
    }
    for golden in load_golden_sessions(session_dir):
        actual_answers = generate_factor_answers(golden.session)
        for factor_id in EXPECTED_GOLDEN_FACTOR_IDS:
            answer_pairs[factor_id].append(
                (golden.expected_factor_results[factor_id], actual_answers[factor_id])
            )
    return [
        score_factor_answers(factor_id, answer_pairs[factor_id])
        for factor_id in sorted(EXPECTED_GOLDEN_FACTOR_IDS)
    ]


def score_factor_answers(
    factor_id: str,
    answer_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> FactorScore:
    expected_atoms: Counter[tuple[Any, ...]] = Counter()
    actual_atoms: Counter[tuple[Any, ...]] = Counter()
    for session_index, (expected, actual) in enumerate(answer_pairs):
        expected_atoms.update(_answer_atoms(factor_id, expected, session_index=session_index))
        actual_atoms.update(_answer_atoms(factor_id, actual, session_index=session_index))

    true_positive = sum((expected_atoms & actual_atoms).values())
    false_positive = sum((actual_atoms - expected_atoms).values())
    false_negative = sum((expected_atoms - actual_atoms).values())
    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    f1 = 0.0 if precision + recall == 0.0 else (2.0 * precision * recall) / (precision + recall)
    return FactorScore(
        factor_id=factor_id,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
    )


def scores_meet_threshold(scores: list[FactorScore], *, threshold: float) -> bool:
    return bool(scores) and all(score.f1 >= threshold for score in scores)


def _answer_atoms(
    factor_id: str,
    answer: Mapping[str, Any],
    *,
    session_index: int,
) -> Counter[tuple[Any, ...]]:
    atoms: Counter[tuple[Any, ...]] = Counter()
    if factor_id == "official.task-completion":
        atoms[(session_index, "verdict", str(answer.get("verdict") or "unknown"))] += 1
        atoms[(session_index, "verification", str(answer.get("verification") or "none"))] += 1
        for event_id in answer.get("evidence_event_ids") or []:
            atoms[(session_index, "evidence", str(event_id))] += 1
        return atoms

    records_key = {
        "official.user-input-sentiment": "events",
        "official.repeated-request": "chains",
        "official.tool-failure-frequency": "tools",
        "official.session-resource-usage": "resources",
        "official.key-sentence-trends": "phrases",
        "official.semantic-phrase-clusters": "clusters",
    }.get(factor_id)
    if records_key is None:
        raise ValueError(f"unsupported Golden score factor: {factor_id}")

    records = answer.get(records_key)
    if not isinstance(records, list) or not records:
        return atoms

    for record in records:
        if not isinstance(record, Mapping):
            continue
        if factor_id == "official.user-input-sentiment":
            atoms[(session_index, "event", str(record.get("event_id") or ""), str(record.get("kind") or ""))] += 1
        elif factor_id == "official.repeated-request":
            atoms[(session_index, "chain", str(record.get("first_event_id") or ""), str(record.get("repeat_event_id") or ""))] += 1
        elif factor_id == "official.tool-failure-frequency":
            atoms[
                (
                    "tool",
                    session_index,
                    str(record.get("tool_name") or ""),
                    int(record.get("failure_count") or 0),
                    int(record.get("recovered_count") or 0),
                    int(record.get("unrecovered_count") or 0),
                )
            ] += 1
        elif factor_id == "official.session-resource-usage":
            atoms[
                (
                    "resource",
                    session_index,
                    str(record.get("resource_type") or ""),
                    str(record.get("resource_name") or ""),
                    int(record.get("count") or 0),
                )
            ] += 1
        elif factor_id == "official.key-sentence-trends":
            atoms[
                (
                    "phrase",
                    session_index,
                    str(record.get("label") or ""),
                    str(record.get("relation_type") or ""),
                )
            ] += max(1, int(record.get("count") or 0))
        elif factor_id == "official.semantic-phrase-clusters":
            cluster_id = str(record.get("cluster_id") or "")
            atoms[(session_index, "cluster", cluster_id)] += 1
            atoms[(session_index, "cluster-label", cluster_id, str(record.get("label") or ""))] += 1
            atoms[(session_index, "cluster-turn-count", cluster_id, int(record.get("turn_count") or 0))] += 1
            for variant in record.get("variants") or []:
                atoms[(session_index, "variant", cluster_id, str(variant))] += 1
    return atoms


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 1.0


def generate_factor_answers(session: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    factors = {factor.factor_id: factor for factor in _load_official_factors()}
    return {
        factor_id: project_factor_answer(factors[factor_id].evaluate(session))
        for factor_id in sorted(EXPECTED_GOLDEN_FACTOR_IDS)
    }


def project_factor_answer(result: OfficialFactorResult) -> dict[str, Any]:
    projector = {
        "official.task-completion": _project_task_completion,
        "official.user-input-sentiment": _project_user_sentiment,
        "official.repeated-request": _project_repeated_request,
        "official.tool-failure-frequency": _project_tool_failures,
        "official.session-resource-usage": _project_resource_usage,
        "official.key-sentence-trends": _project_key_sentences,
        "official.semantic-phrase-clusters": _project_semantic_clusters,
    }.get(result.factor_id)
    if projector is None:
        raise ValueError(f"unsupported golden factor: {result.factor_id}")
    return projector(result)


def _load_golden_session(path: Path) -> GoldenSession:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "evozeus.session-golden.v1":
        raise ValueError(f"{path}: invalid schema_version")
    expected = payload.get("expected_factor_results")
    if not isinstance(expected, Mapping):
        raise ValueError(f"{path}: expected_factor_results must be an object")
    factor_ids = set(str(key) for key in expected)
    missing = sorted(EXPECTED_GOLDEN_FACTOR_IDS - factor_ids)
    extra = sorted(factor_ids - EXPECTED_GOLDEN_FACTOR_IDS)
    if missing:
        raise ValueError(f"{path}: missing factor answers: {', '.join(missing)}")
    if extra:
        raise ValueError(f"{path}: unknown factor answers: {', '.join(extra)}")
    session = payload.get("session")
    if not isinstance(session, Mapping):
        raise ValueError(f"{path}: session must be an object")
    return GoldenSession(
        golden_id=str(payload.get("golden_id") or path.stem),
        source_path=path,
        display_title=str(payload.get("display_title") or ""),
        source_note=str(payload.get("source_note") or ""),
        review_note=str(payload.get("review_note") or ""),
        review_status=str(payload.get("review_status") or ""),
        provenance=payload.get("provenance") if isinstance(payload.get("provenance"), Mapping) else {},
        session=session,
        expected_factor_results={str(key): value for key, value in expected.items() if isinstance(value, Mapping)},
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_official_factors() -> list[OfficialFactor]:
    factors: list[OfficialFactor] = []
    for factor_dir in sorted(path for path in factors_root().iterdir() if path.is_dir()):
        module_name = f"evozeus_golden_factor_{factor_dir.name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, factor_dir / "factor.py")
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load official factor: {factor_dir}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        factor_class = next(
            value
            for value in module.__dict__.values()
            if isinstance(value, type) and issubclass(value, OfficialFactor) and value is not OfficialFactor
        )
        factors.append(factor_class())
    if {factor.factor_id for factor in factors} != EXPECTED_GOLDEN_FACTOR_IDS:
        raise ValueError("loaded official Factor set does not match Golden Factor set")
    return factors


def _project_task_completion(result: OfficialFactorResult) -> dict[str, Any]:
    verdict = str(result.statistics.get("verdict") or _tag_value(result, "task_completion") or "unknown")
    verification = str(result.statistics.get("verification") or _default_verification(verdict))
    return {
        "status": result.status,
        "verdict": verdict,
        "verification": verification,
        "evidence_event_ids": _evidence_ids(result),
    }


def _project_user_sentiment(result: OfficialFactorResult) -> dict[str, Any]:
    records = _records(result, "user_sentiment")
    events = [
        {"event_id": str(record.get("event_id") or ""), "kind": str(record.get("sentiment_kind") or "")}
        for record in records
        if str(record.get("sentiment_kind") or "") != "neutral_request"
    ]
    return {"status": result.status, "events": events, "evidence_event_ids": _evidence_ids(result)}


def _project_repeated_request(result: OfficialFactorResult) -> dict[str, Any]:
    chains = [
        {
            "first_event_id": str(record.get("first_event_id") or ""),
            "repeat_event_id": str(record.get("repeat_event_id") or ""),
        }
        for record in _records(result, "evidence_record_set")
    ]
    return {"status": result.status, "chains": chains, "evidence_event_ids": _evidence_ids(result)}


def _project_tool_failures(result: OfficialFactorResult) -> dict[str, Any]:
    tools = [
        {
            "tool_name": str(record.get("tool_name") or ""),
            "failure_count": _int_field(record, "failure_count", "count"),
            "recovered_count": _int_field(record, "recovered_count"),
            "unrecovered_count": _int_field(record, "unrecovered_count", "count"),
        }
        for record in _records(result, "frequency_distribution")
    ]
    return {"status": result.status, "tools": tools, "evidence_event_ids": _evidence_ids(result)}


def _project_resource_usage(result: OfficialFactorResult) -> dict[str, Any]:
    resources = [
        {
            "resource_type": str(record.get("resource_type") or ""),
            "resource_name": str(record.get("resource_name") or ""),
            "count": int(record.get("count") or 0),
        }
        for record in _records(result, "session_resource_usage")
    ]
    return {"status": result.status, "resources": resources, "evidence_event_ids": _evidence_ids(result)}


def _project_key_sentences(result: OfficialFactorResult) -> dict[str, Any]:
    aggregated: dict[tuple[str, str], int] = {}
    for record in _records(result, "key_sentence_trend"):
        key = (str(record.get("cluster_label") or ""), str(record.get("relation_type") or ""))
        aggregated[key] = aggregated.get(key, 0) + int(record.get("count") or 0)
    phrases = [
        {"label": label, "relation_type": relation_type, "count": count}
        for (label, relation_type), count in aggregated.items()
    ]
    return {"status": result.status, "phrases": phrases, "evidence_event_ids": _evidence_ids(result)}


def _project_semantic_clusters(result: OfficialFactorResult) -> dict[str, Any]:
    clusters = [
        {
            "cluster_id": str(record.get("cluster_id") or ""),
            "label": str(record.get("label") or ""),
            "variants": [str(value) for value in record.get("variants") or []],
            "turn_count": int(record.get("turn_count") or 0),
        }
        for record in _records(result, "semantic_phrase_cluster_set")
    ]
    return {"status": result.status, "clusters": clusters, "evidence_event_ids": _evidence_ids(result)}


def _records(result: OfficialFactorResult, semantic_type: str) -> list[Mapping[str, Any]]:
    return [
        record
        for dataset in result.datasets
        if dataset.semantic_type == semantic_type
        for record in dataset.records
    ]


def _evidence_ids(result: OfficialFactorResult) -> list[str]:
    return sorted({str(ref.get("ref_id") or "") for ref in result.evidence_refs if ref.get("ref_id")})


def _tag_value(result: OfficialFactorResult, tag_type: str) -> str:
    for tag in result.tags:
        if tag.get("type") == tag_type:
            return str(tag.get("value") or "")
    return ""


def _default_verification(verdict: str) -> str:
    return {
        "completed": "claimed",
        "blocked": "blocked",
        "not_completed": "none",
        "unknown": "none",
    }.get(verdict, "none")


def _int_field(record: Mapping[str, Any], key: str, fallback_key: str = "") -> int:
    if key in record:
        return int(record[key])
    if fallback_key and fallback_key in record:
        return int(record[fallback_key])
    return 0
