# Official Factor Packs

每个 pack 必须是 maintainer-promoted asset，不接收未经 `evozeus-factor-lab` review 的普通投稿。

建议结构：

```text
packs/<pack-id>/
  README.md
  pack.yaml
  factors/
  examples/
  tests/
```

命名规则：

- `pack-id` 使用 lower kebab-case。
- 官方 domain pack 建议使用 `evozeus-<domain>-pack`。
- pack 内不得包含 raw private session、secret、客户资料或内部路径。
