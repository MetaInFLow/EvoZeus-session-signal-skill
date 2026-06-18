# Checksums

每个 official release 必须提供 checksum。

建议路径：

```text
checksums/<pack-id>/<version>.sha256
```

规则：

- checksum 文件名必须与 release tag 一致。
- checksum 对象必须与 manifest 中声明的 artifact 一致。
- 任何 checksum 变更都需要重新发布 tag 或撤回 release；不能静默覆盖。
