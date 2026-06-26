from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from typing import Any, Mapping


FACTOR_ID = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*$")
SEMVER = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$")
RESULT_STATUSES = {"matched", "not_matched", "skipped", "error"}


@dataclass(frozen=True)
class OfficialFactorInput:
    schema_version: str = "official.factor_input.v0"
    input_kind: str = "session"
    target: Mapping[str, Any] = field(default_factory=dict)
    records: list[Mapping[str, Any]] = field(default_factory=list)
    prior_results: list[Mapping[str, Any]] = field(default_factory=list)
    context: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_kind": self.input_kind,
            "target": dict(self.target),
            "records": [dict(record) for record in self.records],
            "prior_results": [dict(result) for result in self.prior_results],
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class OfficialResultDataset:
    id: str
    semantic_type: str
    shape: str
    primary_key: str = ""
    records: list[Mapping[str, Any]] = field(default_factory=list)
    schema: Mapping[str, str] = field(default_factory=dict)
    evidence_policy: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "semantic_type": self.semantic_type,
            "shape": self.shape,
            "primary_key": self.primary_key,
            "records": [dict(record) for record in self.records],
            "schema": dict(self.schema),
            "evidence_policy": dict(self.evidence_policy),
        }


@dataclass(frozen=True)
class OfficialResultPresentation:
    id: str
    title: str
    component_ref: str
    data_ref: str
    bindings: Mapping[str, str] = field(default_factory=dict)
    props: Mapping[str, Any] = field(default_factory=dict)
    routes: list[str] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)
    priority: int = 100

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "component_ref": self.component_ref,
            "data_ref": self.data_ref,
            "bindings": dict(self.bindings),
            "props": dict(self.props),
            "routes": self.routes,
            "fallback": self.fallback,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class OfficialFactorResult:
    schema_version: str
    factor_id: str
    version: str
    status: str
    target_type: str = "session"
    target_id: str = ""
    stage: str = "signal_extraction"
    confidence: float = 0.0
    tags: list[Mapping[str, str]] = field(default_factory=list)
    scores: Mapping[str, float] = field(default_factory=dict)
    statistics: Mapping[str, Any] = field(default_factory=dict)
    datasets: list[OfficialResultDataset] = field(default_factory=list)
    presentations: list[OfficialResultPresentation] = field(default_factory=list)
    verdict_signals: list[str] = field(default_factory=list)
    evidence_refs: list[Mapping[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "factor_id": self.factor_id,
            "version": self.version,
            "status": self.status,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "stage": self.stage,
            "confidence": self.confidence,
            "tags": [dict(tag) for tag in self.tags],
            "scores": dict(self.scores),
            "statistics": dict(self.statistics),
            "datasets": [dataset.as_dict() for dataset in self.datasets],
            "presentations": [presentation.as_dict() for presentation in self.presentations],
            "verdict_signals": self.verdict_signals,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "notes": self.notes,
        }


class OfficialFactor(ABC):
    spec: Mapping[str, Any]

    def __init__(self, spec: Mapping[str, Any]) -> None:
        assert_valid_official_factor_spec(spec)
        self.spec = dict(spec)

    @property
    def factor_id(self) -> str:
        return str(self.spec["factor_id"])

    @property
    def version(self) -> str:
        return str(self.spec["version"])

    @property
    def title(self) -> str:
        return str(self.spec["title"])

    @abstractmethod
    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        """Evaluate a normalized factor context and return an OfficialFactorResult."""

    def build_result(
        self,
        *,
        status: str = "not_matched",
        target_type: str = "session",
        target_id: str = "",
        stage: str = "signal_extraction",
        confidence: float = 0.0,
        tags: list[Mapping[str, str]] | None = None,
        scores: Mapping[str, float] | None = None,
        statistics: Mapping[str, Any] | None = None,
        datasets: list[Mapping[str, Any] | OfficialResultDataset] | None = None,
        presentations: list[Mapping[str, Any] | OfficialResultPresentation] | None = None,
        verdict_signals: list[str] | None = None,
        evidence_refs: list[Mapping[str, str]] | list[str] | None = None,
        notes: list[str] | None = None,
    ) -> OfficialFactorResult:
        if status not in RESULT_STATUSES:
            raise ValueError("official factor result status must be matched, not_matched, skipped, or error")

        evidence = _evidence_refs(evidence_refs)

        if status == "matched" and not evidence:
            raise ValueError("matched official factor result must include evidence_refs")

        dataset_items = [_dataset(item) for item in (datasets or [])]
        presentation_items = [_presentation(item) for item in (presentations or [])]

        return OfficialFactorResult(
            schema_version=str(self.spec["schema_version"]),
            factor_id=self.factor_id,
            version=self.version,
            status=status,
            target_type=target_type,
            target_id=target_id,
            stage=stage,
            confidence=max(0.0, min(1.0, float(confidence))),
            tags=_mapping_list(tags),
            scores={str(key): float(value) for key, value in dict(scores or {}).items()},
            statistics=dict(statistics or {}),
            datasets=dataset_items,
            presentations=presentation_items,
            verdict_signals=_text_list(verdict_signals),
            evidence_refs=evidence,
            notes=_text_list(notes),
        )


def validate_official_factor_spec(spec: Mapping[str, Any] | Any) -> list[str]:
    issues: list[str] = []

    if not isinstance(spec, Mapping):
        return ["official factor spec must be an object"]

    _require_text(spec.get("schema_version"), "schema_version", issues)

    if spec.get("stability") != "official":
        issues.append("stability must be official")

    if not FACTOR_ID.match(str(spec.get("factor_id", ""))):
        issues.append("factor_id must use lower dot/kebab-case")

    if not SEMVER.match(str(spec.get("version", ""))):
        issues.append("version must use semver like v0.1.0")

    _require_text(spec.get("title"), "title", issues)
    _require_text(spec.get("summary"), "summary", issues)
    _validate_i18n_text(spec.get("title_i18n"), "title_i18n", issues)
    _validate_i18n_text(spec.get("summary_i18n"), "summary_i18n", issues)
    _validate_compatibility(spec.get("compatibility"), issues)
    _validate_governance(spec.get("governance"), issues)
    _validate_input_contract(spec.get("input_contract"), issues)
    _validate_evidence_contract(spec.get("evidence_contract"), issues)
    _validate_output_contract(spec.get("output_contract"), issues)

    test_vectors = spec.get("test_vectors")
    if not isinstance(test_vectors, list) or len(test_vectors) == 0:
        issues.append("test_vectors must include at least one test vector")

    return issues


def assert_valid_official_factor_spec(spec: Mapping[str, Any] | Any) -> None:
    issues = validate_official_factor_spec(spec)
    if issues:
        raise ValueError("invalid official factor spec:\n" + "\n".join(issues))


def _validate_compatibility(value: Any, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append("compatibility is required")
        return

    _require_text(value.get("evozeus_protocol"), "compatibility.evozeus_protocol", issues)


def _validate_governance(value: Any, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append("governance is required")
        return

    _require_text(value.get("owner"), "governance.owner", issues)


def _validate_i18n_text(value: Any, path: str, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append(f"{path} is required")
        return

    _require_text(value.get("zh-CN"), f"{path}.zh-CN", issues)
    _require_text(value.get("en-US"), f"{path}.en-US", issues)


def _validate_input_contract(value: Any, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append("input_contract is required")
        return

    _require_text(value.get("event_model"), "input_contract.event_model", issues)
    _require_text_list(value.get("required_fields"), "input_contract.required_fields", issues)
    _require_text_list(value.get("accepted_input_kinds"), "input_contract.accepted_input_kinds", issues)
    _require_text_list(value.get("target_types"), "input_contract.target_types", issues)
    _require_text_list(value.get("record_types"), "input_contract.record_types", issues)


def _validate_evidence_contract(value: Any, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append("evidence_contract is required")
        return

    _require_text(value.get("ref_format"), "evidence_contract.ref_format", issues)
    _require_text(value.get("privacy"), "evidence_contract.privacy", issues)


def _validate_output_contract(value: Any, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append("output_contract is required")
        return

    _require_text_list(value.get("statuses"), "output_contract.statuses", issues)
    _require_text_list(value.get("fields"), "output_contract.fields", issues)
    _require_text_list(value.get("dataset_semantic_types"), "output_contract.dataset_semantic_types", issues)
    _require_text_list(value.get("presentation_components"), "output_contract.presentation_components", issues)


def _require_text(value: Any, path: str, issues: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{path} is required")


def _require_text_list(value: Any, path: str, issues: list[str]) -> None:
    if not isinstance(value, list) or not _text_list(value):
        issues.append(f"{path} must include at least one string")


def _text_list(value: list[str] | None | Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, str) and item.strip()]


def _mapping_list(value: list[Mapping[str, str]] | None | Any) -> list[Mapping[str, str]]:
    if not isinstance(value, list):
        return []

    return [{str(key): str(item[key]) for key in item} for item in value if isinstance(item, Mapping)]


def _evidence_refs(value: list[Mapping[str, str]] | list[str] | None | Any) -> list[Mapping[str, str]]:
    if not isinstance(value, list):
        return []

    refs: list[Mapping[str, str]] = []
    for item in value:
        if isinstance(item, Mapping):
            refs.append({str(key): str(item[key]) for key in item})
        elif isinstance(item, str) and item.strip():
            ref_id = item.removeprefix("event:")
            refs.append({"ref_id": ref_id, "kind": "event"})
    return refs


def _dataset(value: Mapping[str, Any] | OfficialResultDataset) -> OfficialResultDataset:
    if isinstance(value, OfficialResultDataset):
        return value

    return OfficialResultDataset(
        id=str(value.get("id", "")),
        semantic_type=str(value.get("semantic_type", "")),
        shape=str(value.get("shape", "")),
        primary_key=str(value.get("primary_key", "")),
        records=list(value.get("records", [])) if isinstance(value.get("records"), list) else [],
        schema=dict(value.get("schema", {})) if isinstance(value.get("schema"), Mapping) else {},
        evidence_policy=dict(value.get("evidence_policy", {})) if isinstance(value.get("evidence_policy"), Mapping) else {},
    )


def _presentation(value: Mapping[str, Any] | OfficialResultPresentation) -> OfficialResultPresentation:
    if isinstance(value, OfficialResultPresentation):
        return value

    return OfficialResultPresentation(
        id=str(value.get("id", "")),
        title=str(value.get("title", "")),
        component_ref=str(value.get("component_ref", "")),
        data_ref=str(value.get("data_ref", "")),
        bindings={str(key): str(item) for key, item in dict(value.get("bindings", {})).items()}
        if isinstance(value.get("bindings"), Mapping)
        else {},
        props=dict(value.get("props", {})) if isinstance(value.get("props"), Mapping) else {},
        routes=_text_list(value.get("routes")),
        fallback=_text_list(value.get("fallback")),
        priority=int(value.get("priority", 100) or 100),
    )
