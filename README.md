# evozeus-factors-official

Official EvoZeus Factor packs 的可信发布源。

这个 repo 的任务不是孵化想法，而是发布已经经过 maintainer promotion 的 Factor pack，并让 `EvoZeus` 主 registry 和未来 runtime 能通过 immutable manifest 审计、引用和安装。

```text
factor-lab/reviewed
  -> promotion PR
  -> official pack release
  -> manifest + checksum + SBOM/attestation
  -> EvoZeus main registry pointer
  -> runtime selective install
```

## What It Is

`evozeus-factors-official` 是 official release source。

它负责回答：

- 这个 pack 是否来自 reviewed lab asset。
- 这个 release 是否绑定 tag、manifest、checksum 和 attestation。
- `EvoZeus` main registry 应该引用哪个 immutable release。
- runtime consumer 如何判断这个 pack 是否可信。
- release 如果出问题，如何 deprecate、yank 或 rollback。

## What It Is Not

本 repo 不承担这些职责：

- 不接收普通 Factor 投稿。
- 不做 Factor idea incubation。
- 不追踪 `evozeus-factor-lab` moving branch。
- 不作为绕过主 repo governance 的发布通道。
- 不存 raw private session、secret、客户资料或未脱敏 evidence。

## Start Here

如果你是 maintainer，要发一个 official Factor release：

1. 确认来源在 `evozeus-factor-lab/reviewed/...`。
2. 在 `packs/<pack-id>/` 准备 pack 内容。
3. 在 `manifests/releases/<pack-id>/<version>.yaml` 准备 release manifest。
4. 在 `checksums/<pack-id>/<version>.sha256` 准备 checksum。
5. 在 `attestations/<pack-id>/` 准备 SBOM / attestation。
6. 通过 `scripts/README.md` 的 release verification。
7. 打 tag。
8. 向 `EvoZeus` 主 repo 提交 registry pointer PR。

给 Agent 的最短指令：

```text
Read evozeus-factors-official/README.md and prepare an official Factor pack release checklist. Verify source_review, manifest path, checksum path, attestation path, version tag, compatibility, and main registry publication plan. Do not invent reviewed status.
```

## Who Should Use This

| Role | Use this repo when | Stop when |
| --- | --- | --- |
| Release operator | reviewed lab asset 已准备 promotion | 缺少 manifest、checksum、attestation 或 tag plan |
| Factor maintainer | 要把 reviewed asset 变成 official pack | source review 或 compatibility 不清楚 |
| Security reviewer | pack 含 scanner 或可执行逻辑 | permission、dependency、SBOM 不可复核 |
| Runtime maintainer | 要消费 official pack | release 不是 immutable 或未进入 main registry |

## Consumer Path

Runtime 或 registry consumer 不应该直接读 branch。

可信消费路径是：

```text
EvoZeus main registry
  -> official release manifest
  -> checksum
  -> attestation / SBOM
  -> pack artifact
```

Consumer 必须能回答：

- 这个 pack 的 version 是什么。
- checksum 验证对象是什么。
- compatibility 范围是什么。
- review_state 是 `promoted`、`deprecated` 还是 `yanked`。
- release 是否来自 reviewed lab asset。

## Promotion Contract

从 `evozeus-factor-lab` 进入 official 必须满足：

| Gate | Requirement |
| --- | --- |
| Source review | 指向 `evozeus-factor-lab/reviewed/...` |
| Evidence | 可公开复核，不依赖 raw private session |
| Privacy | 无 secret、客户资料、内部 URL、私有路径 |
| Security | scanner / executable pack 经过 permission 和 dependency review |
| Manifest | 符合 `schemas/release-manifest.schema.json` |
| Release | version、tag、manifest、checksum、attestation 一致 |
| Registry | 有 `EvoZeus` main registry publication plan |

## Release Gate

发布前检查：

- [ ] `pack_id` 使用 lower kebab-case。
- [ ] `version` 使用 semver tag，例如 `v0.1.0`。
- [ ] manifest 中的 artifact path 存在。
- [ ] checksum 文件存在，且对应 manifest artifact。
- [ ] SBOM / attestation 可被 security reviewer 独立复核。
- [ ] compatibility 范围明确。
- [ ] `review_state` 明确。
- [ ] PR 说明包含 registry pointer 更新计划。

## Directory Map

| Path | Purpose |
| --- | --- |
| `packs/` | official Factor pack 源内容 |
| `manifests/` | release index 和 immutable release manifest |
| `checksums/` | release artifact checksum |
| `attestations/` | SBOM、attestation、供应链说明 |
| `schemas/` | release manifest schema |
| `scripts/` | release verification 说明或脚本 |

## Current Status

- Repo status: private / active shell。
- Public-read target: 首个 official pack release 前。
- Stable install source: not yet。
- Main registry publication: pending future registry schema。

## Not Stable Yet

- 还没有 official pack release。
- 还没有 automated release verification。
- 还没有 main registry schema。
- 还没有 runtime install consumer。

## Validation

```bash
git diff --check
node -e "JSON.parse(require('fs').readFileSync('schemas/release-manifest.schema.json','utf8')); console.log('release manifest schema json ok')"
```
