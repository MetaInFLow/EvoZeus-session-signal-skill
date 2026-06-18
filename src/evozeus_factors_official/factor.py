from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from typing import Any, Mapping


FACTOR_ID = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*$")
SEMVER = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$")
RESULT_STATUSES = {"matched", "not_matched", "error"}


@dataclass(frozen=True)
class OfficialFactorResult:
    schema_version: str
    factor_id: str
    version: str
    status: str
    confidence: float = 0.0
    tags: list[str] = field(default_factory=list)
    verdict_signals: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "factor_id": self.factor_id,
            "version": self.version,
            "status": self.status,
            "confidence": self.confidence,
            "tags": self.tags,
            "verdict_signals": self.verdict_signals,
            "evidence_refs": self.evidence_refs,
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
        """Evaluate a normalized session context and return an OfficialFactorResult."""

    def build_result(
        self,
        *,
        status: str = "not_matched",
        confidence: float = 0.0,
        tags: list[str] | None = None,
        verdict_signals: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> OfficialFactorResult:
        if status not in RESULT_STATUSES:
            raise ValueError("official factor result status must be matched, not_matched, or error")

        evidence = _text_list(evidence_refs)

        if status == "matched" and not evidence:
            raise ValueError("matched official factor result must include evidence_refs")

        return OfficialFactorResult(
            schema_version=str(self.spec["schema_version"]),
            factor_id=self.factor_id,
            version=self.version,
            status=status,
            confidence=max(0.0, min(1.0, float(confidence))),
            tags=_text_list(tags),
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
        issues.append("version must use semver, for example v0.1.0")

    _require_text(spec.get("title"), "title", issues)
    _require_text(spec.get("summary"), "summary", issues)
    _validate_compatibility(spec.get("compatibility"), issues)
    _validate_governance(spec.get("governance"), issues)
    _validate_input_contract(spec.get("input_contract"), issues)
    _validate_evidence_contract(spec.get("evidence_contract"), issues)
    _validate_output_contract(spec.get("output_contract"), issues)

    examples = spec.get("examples")
    if not isinstance(examples, list) or len(examples) == 0:
        issues.append("examples must include at least one example")

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


def _validate_input_contract(value: Any, issues: list[str]) -> None:
    if not isinstance(value, Mapping):
        issues.append("input_contract is required")
        return

    _require_text(value.get("event_model"), "input_contract.event_model", issues)
    _require_text_list(value.get("required_fields"), "input_contract.required_fields", issues)


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
