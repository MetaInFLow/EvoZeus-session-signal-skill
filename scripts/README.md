# Release Verification

这里记录 official pack release 的验证步骤。当前 repo 已提供 `scripts/validate-release-manifest.mjs` 和 `npm test`，用于校验 release unit 的 reviewed source、artifact、checksum、attestation 和 compatibility。

## Required Checks

1. `manifests/releases/<pack-id>/<version>.yaml` 符合 `schemas/release-manifest.schema.json`。
2. manifest 的 `pack_id`、`version`、artifact path 与 Git tag 一致。
3. `checksums/<pack-id>/<version>.sha256` 对应 artifact 内容。
4. checksum 文件中的 artifact path 与 manifest `artifact.path` 一致。
5. SBOM / attestation 可被 security reviewer 独立复核。
6. manifest 记录 `security_review` reviewer 和 date。
7. source review 指向 `evozeus-factor-lab/reviewed/...`，且不是 private moving branch。
8. PR 说明包含 registry publication plan。
9. manifest 中的 `registry_publication_plan` 指向 `MetaInFLow/EvoZeus` 的 `factors/registry/` 路径，并要求通过 PR 发布。

Release 未通过这些检查时，不创建或推进 `EvoZeus` main registry PR。

## Local Test

```bash
npm test
npm run test:release-contract
npm run test:official-factor-runner
npm run test:fixed-factor
npm run test:factor
```
