---
name: evozeus-factors-official
description: Use when preparing, reviewing, verifying, publishing, deprecating, yanking, or routing official EvoZeus Factor pack releases.
---

# EvoZeus Official Factors

Official Factors is the immutable release component for promoted Factor packs. It does not incubate ideas and does not accept ordinary Factor submissions.

## Component Role

```text
evozeus-factor-lab/reviewed
  -> promotion PR
  -> pack
  -> release manifest
  -> checksum
  -> SBOM / attestation
  -> Git tag
  -> EvoZeus registry pointer PR
```

## Start Conditions

Only prepare an official release when:

- source asset is in `evozeus-factor-lab/reviewed`
- source review names reviewer and review date
- evidence is public-safe
- scanner or executable behavior has security review
- release manifest, checksum, SBOM / attestation, and Git tag plan are available

If reviewed status is missing, route back to `evozeus-factor-lab`.

## Release Gate

Verify:

- `pack_id` and `version`
- artifact path and type
- manifest schema
- checksum target and algorithm
- SBOM / attestation packet
- compatibility with EvoZeus protocol and runtime
- review state: `promoted`, `deprecated`, or `yanked`
- registry pointer PR plan

Do not publish from a moving branch or loose files.

## Consumer Contract

Consumers must start from the `EvoZeus` main registry pointer, then verify the official release metadata in this repo. Runtime must not bypass the registry pointer.

## Output Shape

```text
Release unit -> Source review -> Manifest -> Checksum -> Attestation -> Tag -> Registry pointer
```
