# Release Verification

这里先记录 official pack release 的手工验证步骤；后续可沉淀为脚本或 CI。

## Required Checks

1. `manifests/releases/<pack-id>/<version>.yaml` 符合 `schemas/release-manifest.schema.json`。
2. manifest 的 `pack_id`、`version`、artifact path 与 Git tag 一致。
3. `checksums/<pack-id>/<version>.sha256` 对应 artifact 内容。
4. SBOM / attestation 可被 security reviewer 独立复核。
5. source review 指向 `evozeus-factor-lab/reviewed/...`，且不是 private moving branch。
6. PR 说明包含 registry publication plan。

Release 未通过这些检查时，不创建或推进 `EvoZeus` main registry PR。
