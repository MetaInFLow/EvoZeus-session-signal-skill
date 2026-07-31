# Changelog

## [Unreleased]

### Added

- Added the read-only `evozeus.session-signal.lesson-candidate.v1` method and stdin/stdout CLI for high-precision normal Chat correction and durable-rule candidates.
- Added deterministic target selection by registered `cwd` containment or one unique alias, plus bounded model-only natural-language guidance.

### Security

- The companion performs no persistence or network access and never returns raw prompts, local paths or signal identifiers.

## [v0.1.0] - 2026-07-26

### Added

- Session Signal SKILL synthesis method and seven official Factor tools.
- Golden-session evaluation, official Factor contracts, privacy boundaries and packaged resource checks.
- Stable and single-UAT release distribution through the EvoZeus product manifest.

### Verification

- `python -m pytest -q` (97 passed, 2 optional checks skipped, 18 subtests passed).
- `python scripts/validate_official_factor_spec.py factors/*/spec.json`.
