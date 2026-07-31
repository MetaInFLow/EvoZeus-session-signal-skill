# Changelog

## [Unreleased]

The Lesson candidate method and API changes remain Unreleased; the current published package stays at `v0.1.0`. Product attachment, checksum and release ownership remain in the EvoZeus repository.

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
- Preserved direct corrections after an English full-stop attribution clause and durable rules before a separate Chinese or English confirmation tail.
- Excluded hypothetical durable rules and preserved direct corrections joined to attributed text by Chinese or English conjunctions.
- Replaced the component checksum attachment with a method/API-only contract.
- Required an explicit target inventory field and preserved lowercase English corrections after attributed sentences.
- Added deterministic attribution scope parsing with `e.g.` / `i.e.` handling and direct-feedback precedence.
- Extended scope parsing to durable rules, smart apostrophes, and complete unfenced Python traceback blocks.
- Classified pure correction questions, nominal attribution objects, and arbitrary qualified Python exception terminals.
- Added explicit fix-request tails and standalone qualified exception-line filtering.
- Made ordinary commas first-class evidence-scope boundaries and recognized bracketed log levels.
- Added modifier-qualified English miss objects, colon question prefixes, and timestamp-plus-level log headers.
- Preserved sentence-level choice-question scope, tightened Java stack frames, and added common answer subjects.
- Limited choice-question scope to self-doubt forms before comma or semicolon splitting.
- Recognized comma-delimited fractional seconds in pasted log timestamps.
- Stopped inferring unregistered repository basenames as target aliases.
- Preserved durable scope and action across natural Chinese and English comma clauses.
- Generalized reporting-verb attribution to named sources and caller-defined roles.

## [v0.1.0] - 2026-07-26

### Added

- Session Signal SKILL synthesis method and seven official Factor tools.
- Golden-session evaluation, official Factor contracts, privacy boundaries and packaged resource checks.
- Stable and single-UAT release distribution through the EvoZeus product manifest.

### Verification

- `python -m pytest -q` (97 passed, 2 optional checks skipped, 18 subtests passed).
- `python scripts/validate_official_factor_spec.py factors/*/spec.json`.
