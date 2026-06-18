from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples" / "factors"))

from repeated_request import RepeatedRequestFactor  # noqa: E402


class OfficialFactorExamplesTest(unittest.TestCase):
    def test_repeated_request_example_returns_matched_with_evidence_ref(self) -> None:
        session = json.loads((ROOT / "examples" / "sessions" / "repeated-request.json").read_text(encoding="utf-8"))
        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "matched")
        self.assertEqual(result.tags, ["loop:repeated-request"])
        self.assertIn("event:user-2", result.evidence_refs)


if __name__ == "__main__":
    unittest.main()
