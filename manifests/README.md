# Release Manifests

Release manifest 是 `EvoZeus` 主 repo registry 引用 official pack 的稳定入口。

目录结构：

```text
manifests/
  index.yaml
  releases/
    <pack-id>/
      v0.1.0.yaml
```

规则：

- manifest 必须绑定 immutable release artifact。
- version 使用 semver tag，例如 `v0.1.0`。
- checksum、SBOM、attestation 必须与 manifest 中的路径和版本一致。
- 主 repo registry 不引用 moving branch。
