# Changelog

## [Unreleased]

The component attachment declares the intended next component version `v0.1.1`; the current published package remains `v0.1.0` until a separate product release.

### Added

- Added the read-only `evozeus.session-signal.lesson-candidate.v1` method and stdin/stdout CLI for high-precision normal Chat correction and durable-rule candidates.
- Added deterministic target selection by registered `cwd` containment or one unique alias, plus bounded model-only natural-language guidance.

### Security

- The companion performs no persistence or network access and never returns raw prompts, local paths or signal identifiers.

### Fixed

- Preserved English contractions and direct corrections about quoted files during prose de-noising.
- Preserved a durable rule that is followed by a confirmation question in the same clause.
- Excluded hypothetical corrections inside Chinese and English conditional clauses while preserving direct corrections outside their scope.
- Removed Markdown fenced blocks using same-character fences of three or more markers and closers at least as long as their opener.

## [v0.1.0] - 2026-07-26

### Added

- Session Signal SKILL synthesis method and seven official Factor tools.
- Golden-session evaluation, official Factor contracts, privacy boundaries and packaged resource checks.
- Stable and single-UAT release distribution through the EvoZeus product manifest.

### Verification

- `python -m pytest -q` (97 passed, 2 optional checks skipped, 18 subtests passed).
- `python scripts/validate_official_factor_spec.py factors/*/spec.json`.
