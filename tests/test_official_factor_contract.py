from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_factors_official import OfficialFactor, OfficialFactorInput, validate_official_factor_spec  # noqa: E402


def _load_factor_module(slug: str):
    path = ROOT / "factors" / slug / "factor.py"
    spec = importlib.util.spec_from_file_location(f"official_factor_{slug.replace('-', '_')}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load official factor: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_repeated_request = _load_factor_module("repeated-request")
OFFICIAL_REPEATED_REQUEST_SPEC = _repeated_request.OFFICIAL_REPEATED_REQUEST_SPEC
RepeatedRequestFactor = _repeated_request.RepeatedRequestFactor


class OfficialFactorContractTest(unittest.TestCase):
    def test_official_factor_cannot_be_instantiated_without_evaluate(self) -> None:
        with self.assertRaises(TypeError):
            OfficialFactor(OFFICIAL_REPEATED_REQUEST_SPEC)  # type: ignore[abstract]

    def test_validates_required_official_spec_surface(self) -> None:
        self.assertEqual(validate_official_factor_spec(OFFICIAL_REPEATED_REQUEST_SPEC), [])

    def test_rejects_non_official_stability(self) -> None:
        spec = dict(OFFICIAL_REPEATED_REQUEST_SPEC)
        spec["stability"] = "lab"
        issues = validate_official_factor_spec(spec)

        self.assertIn("stability must be official", "\n".join(issues))

    def test_requires_governance_and_compatibility(self) -> None:
        spec = dict(OFFICIAL_REPEATED_REQUEST_SPEC)
        spec.pop("governance")
        spec.pop("compatibility")
        issues = "\n".join(validate_official_factor_spec(spec))

        self.assertIn("governance", issues)
        self.assertIn("compatibility", issues)

    def test_requires_bilingual_title_and_summary(self) -> None:
        spec = dict(OFFICIAL_REPEATED_REQUEST_SPEC)
        spec.pop("title_i18n")
        spec["summary_i18n"] = {"zh-CN": "只有中文说明"}
        issues = "\n".join(validate_official_factor_spec(spec))

        self.assertIn("title_i18n", issues)
        self.assertIn("summary_i18n.en-US", issues)

    def test_requires_matched_results_to_include_evidence_refs(self) -> None:
        factor = RepeatedRequestFactor()

        with self.assertRaisesRegex(ValueError, "evidence_refs"):
            factor.build_result(status="matched")

    def test_result_serializes_datasets_and_presentations(self) -> None:
        factor = RepeatedRequestFactor()

        result = factor.build_result(
            status="matched",
            target_type="session",
            target_id="session-1",
            scores={"repeated_request_count": 1.0},
            datasets=[
                {
                    "id": "repeated_request_events",
                    "semantic_type": "evidence_record_set",
                    "shape": "record_set",
                    "primary_key": "event_id",
                    "records": [{"event_id": "user-2", "role": "user"}],
                }
            ],
            presentations=[
                {
                    "id": "repeated_request_table",
                    "title": "Repeated request events",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "repeated_request_events",
                    "bindings": {"row_key": "event_id"},
                    "fallback": ["builtin.json.v1"],
                }
            ],
            evidence_refs=[{"ref_id": "user-2", "kind": "user_turn"}],
        )

        payload = result.as_dict()

        self.assertEqual(payload["target_type"], "session")
        self.assertEqual(payload["target_id"], "session-1")
        self.assertEqual(payload["scores"]["repeated_request_count"], 1.0)
        self.assertEqual(payload["datasets"][0]["semantic_type"], "evidence_record_set")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.table.v1")

    def test_official_factor_input_serializes_mixed_context(self) -> None:
        factor_input = OfficialFactorInput(
            input_kind="mixed_context",
            target={"target_type": "project", "target_id": "project-a", "project_key": "project-a"},
            records=[
                {
                    "record_type": "session_envelope",
                    "record_id": "session-1",
                    "payload": {"session_id": "session-1", "events": []},
                }
            ],
            prior_results=[
                {
                    "factor_id": "official.repeated-request",
                    "target_type": "session",
                    "target_id": "session-1",
                    "status": "matched",
                }
            ],
            context={"time_window": "all"},
        )

        payload = factor_input.as_dict()

        self.assertEqual(payload["input_kind"], "mixed_context")
        self.assertEqual(payload["target"]["target_type"], "project")
        self.assertEqual(payload["records"][0]["record_type"], "session_envelope")
        self.assertEqual(payload["prior_results"][0]["status"], "matched")

    def test_requires_input_kinds_target_types_and_presentation_support(self) -> None:
        spec = dict(OFFICIAL_REPEATED_REQUEST_SPEC)
        spec["input_contract"] = {
            "event_model": "SessionEvent[]",
            "required_fields": ["events[].id"],
        }
        spec["output_contract"] = {
            "statuses": ["matched", "not_matched", "error"],
            "fields": ["tags", "evidence_refs"],
        }

        issues = "\n".join(validate_official_factor_spec(spec))

        self.assertIn("input_contract.accepted_input_kinds", issues)
        self.assertIn("input_contract.target_types", issues)
        self.assertIn("input_contract.record_types", issues)
        self.assertIn("output_contract.dataset_semantic_types", issues)
        self.assertIn("output_contract.presentation_components", issues)


if __name__ == "__main__":
    unittest.main()
