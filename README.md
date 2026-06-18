# evozeus-factors-official

Official EvoZeus Factor packs, release manifests, checksums, and attestations.

本 repo 用于承载经过 maintainer promotion 的官方 Factor packs。它是 official release 源，但 main registry publication 仍由 `EvoZeus` 主 repo 控制。

## 边界

- 发布 official Factor packs、release manifest、checksums、SBOM 和 attestation。
- 接收来自 `evozeus-factor-lab` 的 promotion PR。
- 为 `EvoZeus` 主 repo 的 registry 提供稳定 manifest 引用。
- 不接收未经 lab review 的普通投稿。

## 目录结构

- `packs/`：官方 Factor pack 源内容。
- `manifests/`：release manifest 和 index 草稿。
- `checksums/`：发布产物 checksum。
- `attestations/`：SBOM、artifact attestation 和供应链说明。

## 发布原则

1. official release 必须绑定 Git tag。
2. release manifest 必须包含版本、checksum、兼容范围和 review state。
3. main registry 只引用 release manifest，不追踪 moving branch。
