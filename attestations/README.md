# Attestations

这里存放 official release 的 SBOM、artifact attestation 和供应链说明。

建议路径：

```text
attestations/<pack-id>/<version>.sbom.json
attestations/<pack-id>/<version>.attestation.json
```

规则：

- scanner 或可执行 pack 必须有更严格的依赖和权限说明。
- attestation 必须能被 security reviewer 独立复核。
- private context 不应出现在 SBOM 或 attestation 中。
