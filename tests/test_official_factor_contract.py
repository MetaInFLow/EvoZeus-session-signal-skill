from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorInput, validate_official_factor_spec  # noqa: E402


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

EXPECTED_OFFICIAL_FACTOR_SLUGS = {
    "key-sentence-trends",
    "repeated-request",
    "session-resource-usage",
    "task-completion",
    "tool-failure-frequency",
    "usage-sentence-cloud",
    "user-input-sentiment",
}


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

    def test_every_official_factor_has_source_factor_xml_contract(self) -> None:
        factor_dirs = {path.name: path for path in (ROOT / "factors").iterdir() if path.is_dir()}

        self.assertEqual(set(factor_dirs), EXPECTED_OFFICIAL_FACTOR_SLUGS)
        for slug, factor_dir in factor_dirs.items():
            with self.subTest(slug=slug):
                xml_path = factor_dir / "FACTOR.xml"
                self.assertTrue(xml_path.is_file(), f"missing {xml_path}")
                root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
                self.assertEqual(root.tag, "factor")
                self.assertTrue(root.attrib.get("id", "").startswith("official."))
                self.assertRegex(root.attrib.get("version", ""), r"^v?\d+\.\d+\.\d+")
                self.assertTrue(root.findtext("owner"))
                self.assertTrue(root.find("input_channels/channel") is not None)
                self.assertTrue(root.find("output_datasets/dataset") is not None)
                self.assertTrue(root.find("presentations/presentation") is not None)
                self.assertTrue(root.find("dependencies/package") is not None)
                self.assertTrue(root.find("evidence_policy/raw_body_allowed") is not None)
                self.assertTrue(root.find("quality_notes") is not None)

    def test_top_level_skill_defines_skill_candidate_method_layer(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("chat records -> scanner normalization -> factor signals -> ledger read model", skill_text)
        self.assertIn("factor.py` is the analysis component for chat records", skill_text)
        self.assertIn("proposed verdict -> artifact route -> presentation", skill_text)
        self.assertIn("finding AI collaboration history", skill_text)
        self.assertIn("SKILL Candidate Synthesis Method", skill_text)
        self.assertIn("success_skill_candidate", skill_text)
        self.assertIn("problem_skill_candidate", skill_text)
        self.assertIn("failure_skill_candidate", skill_text)
        self.assertIn("not_skill_candidate", skill_text)
        self.assertIn("ui.native-static.table.v1", skill_text)

    def test_top_level_skill_requires_high_quality_session_review_page(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("High-Quality Session Review Page", skill_text)
        self.assertIn("high_quality_session", skill_text)
        self.assertIn("low_quality_session", skill_text)
        self.assertIn("factor_result_reasons", skill_text)
        self.assertIn("human_quality_review", skill_text)
        self.assertIn("every analyzed session must receive one of these labels", skill_text)
        self.assertIn("why this session is currently judged high-quality", skill_text)
        self.assertIn("which factor results support that judgment", skill_text)
        self.assertIn("paginated review queue", skill_text)
        self.assertIn("Pagination controls must show current page", skill_text)
        self.assertIn("do not use fixture or mock factor outputs", skill_text)
        self.assertIn('what the user asked', skill_text)
        self.assertIn('what the assistant did', skill_text)
        self.assertIn('which tools/resources were used', skill_text)

    def test_factor_xml_matches_python_factor_identity_and_outputs(self) -> None:
        for slug in EXPECTED_OFFICIAL_FACTOR_SLUGS:
            with self.subTest(slug=slug):
                module = _load_factor_module(slug)
                factor_class = next(
                    value
                    for value in module.__dict__.values()
                    if isinstance(value, type) and issubclass(value, OfficialFactor) and value is not OfficialFactor
                )
                factor = factor_class()
                root = ET.fromstring((ROOT / "factors" / slug / "FACTOR.xml").read_text(encoding="utf-8"))
                xml_outputs = [
                    dataset.attrib["semantic_type"]
                    for dataset in root.findall("output_datasets/dataset")
                    if dataset.attrib.get("semantic_type")
                ]
                spec_outputs = factor.spec["output_contract"]["dataset_semantic_types"]
                xml_presentations = [
                    presentation.attrib["component_ref"]
                    for presentation in root.findall("presentations/presentation")
                    if presentation.attrib.get("component_ref")
                ]
                spec_presentations = factor.spec["output_contract"]["presentation_components"]

                self.assertEqual(root.attrib["id"], factor.factor_id)
                self.assertEqual(root.attrib["version"], factor.version)
                self.assertEqual(xml_outputs, spec_outputs)
                self.assertEqual(xml_presentations, spec_presentations)


if __name__ == "__main__":
    unittest.main()
