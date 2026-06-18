---
name: evozeus-factors-official
description: Use when changing the stable Python EvoZeus OfficialFactor contract, official Factor spec schema, or canonical examples.
---

# EvoZeus Official Factors

Official Factors is the stable contract component for Python EvoZeus Factors.

Use this repo only for:

- the Python `OfficialFactor` abstract class.
- official Factor spec schema.
- canonical examples and test vectors.
- compatibility checks for the official Factor result shape.

Do not use this repo for:

- real business Factor packs.
- lab promotion state.
- release manifests, checksums, SBOMs, or attestations.
- runtime install source.

## Required Work Shape

When changing the official contract:

1. Update `src/evozeus_factors_official/factor.py`.
2. Update `schemas/official-factor-spec.schema.json`.
3. Update canonical examples under `examples/`.
4. Run `python3 -m unittest discover -s tests`.
5. Run `python3 scripts/validate_official_factor_spec.py examples/specs/*.json`.
