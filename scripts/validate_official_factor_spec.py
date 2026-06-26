from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill import validate_official_factor_spec  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: python3 scripts/validate_official_factor_spec.py <spec.json> [...]", file=sys.stderr)
        return 2

    failures: list[str] = []

    for raw_path in argv:
        path = Path(raw_path)
        spec = json.loads(path.read_text(encoding="utf-8"))
        issues = validate_official_factor_spec(spec)

        if issues:
            detail = "\n".join(f"  - {issue}" for issue in issues)
            failures.append(f"{path}\n{detail}")

    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        return 1

    print(f"official factor specs valid: {len(argv)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
