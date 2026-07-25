from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.golden import (  # noqa: E402
    evaluate_golden_sessions,
    load_golden_sessions,
    score_golden_sessions,
    scores_meet_threshold,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Golden Sessions against official Factors.")
    parser.add_argument(
        "--dataset",
        choices=("micro", "real"),
        default="micro",
        help="micro requires exact equality; real uses per-Factor precision/recall/F1",
    )
    parser.add_argument("--threshold", type=float, default=0.9, help="minimum F1 for every real-session Factor")
    args = parser.parse_args()

    directory_name = "real-sessions" if args.dataset == "real" else "sessions"
    session_dir = ROOT / "benchmarks" / "golden" / directory_name
    if args.dataset == "real":
        scores = score_golden_sessions(session_dir)
        print("Factor                                      Precision  Recall     F1     Result")
        for score in scores:
            result = "PASS" if score.f1 >= args.threshold else "FAIL"
            print(
                f"{score.factor_id:<43} "
                f"{score.precision:>8.1%}  {score.recall:>6.1%}  {score.f1:>6.1%}  {result}"
            )
        if scores_meet_threshold(scores, threshold=args.threshold):
            print(f"\nPASS every Factor reached F1 >= {args.threshold:.0%}")
            return 0
        print(f"\nFAIL every Factor must reach F1 >= {args.threshold:.0%}")
        return 1

    failures = evaluate_golden_sessions(session_dir)
    total_sessions = len(load_golden_sessions(session_dir))
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"\n{len(failures)} differences across {total_sessions} Golden Sessions")
        return 1
    print(f"PASS {total_sessions} Golden Sessions x 7 Factors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
