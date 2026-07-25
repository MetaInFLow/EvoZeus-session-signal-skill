from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.golden import EXPECTED_GOLDEN_FACTOR_IDS  # noqa: E402
from evozeus_session_signal_skill.real_golden import apply_human_review  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把真实 Codex Golden 候选与人工审阅答案合并。")
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=ROOT.parents[1] / ".evozeus" / "runtime" / "golden-candidates",
    )
    parser.add_argument(
        "--reviews",
        type=Path,
        default=ROOT / "benchmarks" / "golden" / "real-session-reviews.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "benchmarks" / "golden" / "real-sessions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    review_payload = json.loads(args.reviews.read_text(encoding="utf-8"))
    reviews = review_payload.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        raise ValueError("real session review manifest has no reviews")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for review in reviews:
        if not isinstance(review, dict):
            raise ValueError("real session review must be an object")
        candidate_file = str(review.get("candidate_file") or "")
        candidate_path = args.candidate_dir / candidate_file
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        accepted = {str(value) for value in review.get("accepted_seeded_factors") or []}
        overrides = review.get("answer_overrides")
        if not isinstance(overrides, dict):
            raise ValueError(f"{candidate_file}: answer_overrides must be an object")
        reviewed_factor_ids = accepted | set(str(key) for key in overrides)
        if reviewed_factor_ids != EXPECTED_GOLDEN_FACTOR_IDS:
            raise ValueError(f"{candidate_file}: review decisions must cover all seven Factors")

        candidate_answers = candidate.get("expected_factor_results")
        if not isinstance(candidate_answers, dict):
            raise ValueError(f"{candidate_file}: candidate has no Factor answers")
        final_answers = {
            factor_id: overrides.get(factor_id, candidate_answers[factor_id])
            for factor_id in EXPECTED_GOLDEN_FACTOR_IDS
        }
        finalized = apply_human_review(
            candidate,
            {
                "display_title": review.get("display_title"),
                "review_note": review.get("review_note"),
                "expected_factor_results": final_answers,
            },
        )
        output_path = args.output_dir / candidate_file
        output_path.write_text(
            json.dumps(finalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
