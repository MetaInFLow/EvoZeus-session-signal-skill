from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples" / "factors"))

from evozeus_factors_official import OfficialFactor, validate_official_factor_spec  # noqa: E402
from repeated_request import OFFICIAL_REPEATED_REQUEST_SPEC, RepeatedRequestFactor  # noqa: E402


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

    def test_requires_matched_results_to_include_evidence_refs(self) -> None:
        factor = RepeatedRequestFactor()

        with self.assertRaisesRegex(ValueError, "evidence_refs"):
            factor.build_result(status="matched")


if __name__ == "__main__":
    unittest.main()
