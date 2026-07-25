from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.golden_report import render_report  # noqa: E402


def main() -> int:
    output_path = (
        ROOT.parents[1]
        / ".evozeus"
        / "runtime"
        / "reports"
        / "golden-session-benchmarks"
        / "index.html"
    )
    render_report(
        golden_dir=ROOT / "benchmarks" / "golden" / "real-sessions",
        template_path=ROOT / "templates" / "golden-session-review" / "index.html",
        output_path=output_path,
        logo_path=ROOT / "templates" / "ai-usage-profile-report" / "assets" / "evozeus-gold-512.png",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
