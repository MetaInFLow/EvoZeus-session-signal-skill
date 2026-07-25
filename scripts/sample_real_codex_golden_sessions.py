from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.real_golden import build_real_golden_candidate  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从真实 Codex 主线程生成待人工复核的 Golden 候选。")
    parser.add_argument("sources", nargs="+", type=Path, help="Codex rollout JSONL 文件")
    parser.add_argument(
        "--infra-root",
        type=Path,
        default=ROOT.parent / "EvoZeus-infra",
        help="EvoZeus-infra repo 路径",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT.parents[1] / ".evozeus" / "runtime" / "golden-candidates",
        help="候选 JSON 输出目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    infra_src = args.infra_root.resolve() / "src"
    if not infra_src.is_dir():
        raise FileNotFoundError(f"EvoZeus-infra src not found: {infra_src}")
    sys.path.insert(0, str(infra_src))

    from evozeus_runtime.scanners.base import ScanRequest
    from evozeus_runtime.scanners.providers.codex import CodexScanner

    scanner = CodexScanner()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(args.sources, start=1):
        source = source.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Codex rollout not found: {source}")
        refs = scanner.discover(ScanRequest(provider="codex", source_dir=source.parent))
        ref = next((candidate for candidate in refs if candidate.source_path.resolve() == source), None)
        if ref is None:
            raise ValueError(f"Codex scanner did not discover rollout: {source}")
        envelope = scanner.load(ref).model_dump(mode="json")
        record_date = _record_date_from_filename(source.name)
        short_hash = str(envelope["metadata"].get("source_fingerprint") or "")[-8:]
        golden_id = f"real-{index:02d}-{record_date or 'undated'}-{short_hash}"
        display_title = str(envelope["metadata"].get("session_title") or source.stem)
        candidate = build_real_golden_candidate(
            envelope,
            golden_id=golden_id,
            display_title=display_title,
            source_record_date=record_date,
        )
        output_path = args.output_dir / f"{golden_id}.json"
        output_path.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output_path)
    return 0


def _record_date_from_filename(filename: str) -> str:
    match = re.search(r"rollout-(\d{4}-\d{2}-\d{2})T", filename)
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
