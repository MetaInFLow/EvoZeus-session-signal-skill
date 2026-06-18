# evozeus-factors-official

<p align="center">
  <strong>Immutable release layer for promoted EvoZeus Factor packs.</strong>
</p>

<p align="center">
  <img alt="layer official release" src="https://img.shields.io/badge/layer-official%20release-2563eb?style=flat-square" />
  <img alt="trust immutable manifest" src="https://img.shields.io/badge/trust-immutable%20manifest-16a34a?style=flat-square" />
  <img alt="registry pointer required" src="https://img.shields.io/badge/registry-pointer%20required-f97316?style=flat-square" />
</p>

<p align="center">
  <a href="#start-here">Start Here</a>
  ·
  <a href="#release-unit-model">Release Unit</a>
  ·
  <a href="#use-paths">Use Paths</a>
  ·
  <a href="#trust-protocol">Trust Protocol</a>
  ·
  <a href="#release-gate">Release Gate</a>
  ·
  <a href="#repo-map">Repo Map</a>
</p>

---

## What It Is

`evozeus-factors-official` 是 EvoZeus Factor 的 **official release layer**。

它不孵化 Factor idea，也不判断一个投稿是否值得进入体系。它只做一件事：把已经通过 `evozeus-factor-lab` review 的 asset，封装成可复核、可引用、可撤回的 official release unit。

核心判断：

- Branch content is not a trust source.
- Runtime 不直接消费 lab moving branch。
- `EvoZeus` main registry 不直接引用 loose files。
- Official release 必须同时具备 pack、manifest、checksum、attestation/SBOM、Git tag 和 registry pointer plan。
- 没有 immutable release unit，就没有 official Factor。

```text
evozeus-factor-lab/reviewed
  -> promotion PR
  -> release unit
  -> Git tag
  -> EvoZeus main registry pointer
  -> runtime selective install
```

## What It Is Not

本 repo 不承担这些职责：

- 不接收普通 Factor 投稿。
- 不做 Factor idea incubation。
- 不替代 `evozeus-factor-lab` review。
- 不追踪 `evozeus-factor-lab` moving branch。
- 不作为绕过 `EvoZeus` main registry governance 的发布通道。
- 不存 raw private session、secret、客户资料或未脱敏 evidence。

## Start Here

给 Agent 的最短指令：

```text
Read evozeus-factors-official/README.md and prepare an official Factor release checklist.
Verify source_review, release manifest, checksum, attestation/SBOM, Git tag, compatibility, review_state, and EvoZeus main registry pointer plan.
Do not invent reviewed status. Do not consume branch content as an official release.
```

如果你是 maintainer，要发布一个 official Factor：

1. 确认 source asset 位于 `evozeus-factor-lab/reviewed/...`。
2. 在 `packs/<pack-id>/` 准备 official pack 内容。
3. 在 `manifests/releases/<pack-id>/<version>.yaml` 准备 release manifest。
4. 在 `checksums/<pack-id>/<version>.sha256` 准备 checksum。
5. 在 `attestations/<pack-id>/` 准备 SBOM / attestation。
6. 确认 `version` 与 Git tag 一致，例如 `v0.1.0`。
7. 运行或人工完成 [release verification](scripts/README.md)。
8. 向 `EvoZeus` main repo 提交 registry pointer PR。

正常 consumer 不从这里开始安装。consumer 应该从 `EvoZeus` main registry 读取 pointer，再回到本 repo 校验 manifest、checksum 和 attestation。

## Release Unit Model

Official release 的最小可信对象不是一个目录，而是一个 release unit。

| Object | Answers | Location |
| --- | --- | --- |
| Promoted Lab Asset | 这个 release 从哪个 reviewed asset 来 | `source_review.lab_path` |
| Pack | 被发布的 Factor 内容是什么 | `packs/<pack-id>/` |
| Release Manifest | version、artifact、compatibility、review_state 是什么 | `manifests/releases/<pack-id>/<version>.yaml` |
| Checksum | artifact 是否被篡改 | `checksums/<pack-id>/<version>.sha256` |
| SBOM / Attestation | scanner / executable pack 的供应链和来源如何复核 | `attestations/<pack-id>/` |
| Git Tag | 这次 release 的 immutable git boundary | `vX.Y.Z` |
| Registry Pointer | `EvoZeus` main registry 应该引用哪个 release | main repo registry PR |

Release unit 只有在这些对象能互相指向并通过 verification 时，才算 official。

## Use Paths

| Goal | Start here | Output |
| --- | --- | --- |
| 准备 official release | [Start Here](#start-here) | release checklist |
| 填写 release manifest | [schema](schemas/release-manifest.schema.json) | `manifests/releases/<pack-id>/<version>.yaml` |
| 校验 release | [scripts/README.md](scripts/README.md) | verification result |
| 查看 official pack 内容 | [packs/README.md](packs/README.md) | pack source review |
| 查看 manifest/index 规则 | [manifests/README.md](manifests/README.md) | manifest path and index convention |
| 查看 checksum 规则 | [checksums/README.md](checksums/README.md) | sha256 verification plan |
| 查看 attestation 规则 | [attestations/README.md](attestations/README.md) | SBOM / attestation packet |
| 更新 main registry | `EvoZeus` main repo registry PR | immutable pointer |

## Trust Protocol

可信消费路径必须是：

```text
EvoZeus main registry
  -> release manifest
  -> checksum
  -> attestation / SBOM
  -> pack artifact
```

Consumer 必须能回答：

- `pack_id` 是什么。
- `version` 是否和 Git tag 一致。
- `source_review.lab_path` 是否指向 reviewed lab asset。
- `artifact.path` 是否存在。
- checksum 验证的是哪个 artifact。
- compatibility 范围是否明确。
- `review_state` 是 `promoted`、`deprecated` 还是 `yanked`。
- attestation / SBOM 是否足以让 security reviewer 独立复核。

禁止的 trust shortcut：

- 直接安装 `main` branch。
- 直接引用 `packs/<pack-id>/` 而不读 manifest。
- 从 lab moving branch 跳过 official release。
- 用 README 文字替代 checksum、attestation 或 source review。
- 把 `deprecated` 或 `yanked` release 当作默认可用 release。

## Promotion Contract

从 `evozeus-factor-lab` 进入 official 必须满足：

| Gate | Requirement |
| --- | --- |
| Source review | 指向 `evozeus-factor-lab/reviewed/...`，包含 reviewer 和 review date |
| Evidence | 可公开复核，不依赖 raw private session |
| Privacy | 无 secret、客户资料、内部 URL、私有路径 |
| Security | scanner / executable pack 经过 permission、dependency、sandbox review |
| Manifest | 符合 `schemas/release-manifest.schema.json` |
| Release | version、tag、manifest、checksum、attestation 一致 |
| Registry | 有 `EvoZeus` main registry publication plan |

## Release States

| State | Meaning | Consumer behavior |
| --- | --- | --- |
| `promoted` | 当前可被 registry 指向的 official release | 可选择性安装 |
| `deprecated` | 仍可追溯，但不应作为新默认选择 | 只为兼容或迁移读取 |
| `yanked` | 发现安全、隐私、错误或治理问题 | 不安装；保留审计记录 |

状态变化也必须通过 manifest 或 registry pointer 更新，而不是口头说明。

## Release Gate

发布前检查：

- [ ] `pack_id` 使用 lower kebab-case。
- [ ] `version` 使用 semver tag，例如 `v0.1.0`。
- [ ] `source_review.lab_path` 指向 reviewed lab asset。
- [ ] manifest 中的 artifact path 存在。
- [ ] checksum 文件存在，且对应 manifest artifact。
- [ ] SBOM / attestation 可被 security reviewer 独立复核。
- [ ] compatibility 范围明确。
- [ ] `review_state` 明确。
- [ ] PR 说明包含 `EvoZeus` main registry pointer 更新计划。

基础本地验证：

```bash
git diff --check
python3 -m json.tool schemas/release-manifest.schema.json >/dev/null
```

## Repo Map

| Path | Purpose |
| --- | --- |
| `packs/` | official Factor pack 源内容 |
| `manifests/` | release index 和 immutable release manifest |
| `checksums/` | release artifact checksum |
| `attestations/` | SBOM、attestation、供应链说明 |
| `schemas/` | release manifest schema |
| `scripts/` | release verification 说明或脚本 |

## Relationship To The EvoZeus System

```text
EvoZeus main repo
  public intake, case, verdict, registry governance

evozeus-factor-lab
  quarantine, evidence review, rejected/reviewed state

evozeus-factors-official
  immutable release unit, checksum, attestation, tag

runtime consumer
  selective install from main registry pointer only
```

本 repo 是可信发布层，不是判断层、孵化层或 runtime 默认安装源。

## Visibility Contract

- Web 源码可以 private；本 repo 不是 Web 源码。
- 只要 release manifest、checksum、SBOM、attestation 或 pack artifact 会被用户、agent 或 runtime 消费，本 repo 必须先变为 public。
- 首个 official pack release 不能只存在于 private repo；消费者必须能独立审计 tag、manifest、checksum 和 source review。
- public 不等于自动安装；runtime 仍必须通过 main registry pointer 和用户确认选择性安装。
- private source evidence 不进入 official release；release unit 只引用可公开复核的 source review。

## What Exists Today

| Area | Status |
| --- | --- |
| Release structure | `packs/`、`manifests/`、`checksums/`、`attestations/` 已建立 |
| Manifest schema | `schemas/release-manifest.schema.json` 已存在 |
| Verification docs | `scripts/README.md` 有手工 gate |
| Official releases | 尚未发布首个 pack |
| Main registry pointer | 等待 `EvoZeus` main registry schema 稳定 |

## Not Promised

- 不承诺 `main` branch 可直接安装。
- 不承诺所有 reviewed lab assets 都会 promotion。
- 不承诺 official release 自动进入 main registry。
- 不承诺 scanner pack 可在所有 runtime 环境运行。
- 不承诺公开 repo 会包含 private source evidence。
