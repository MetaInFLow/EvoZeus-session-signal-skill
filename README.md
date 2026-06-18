# evozeus-factors-official

`evozeus-factors-official` 是 EvoZeus Factor 的 **official contract repo**。

它只放三类东西：

1. 稳定 Python `OfficialFactor` 抽象类。
2. 官方 Factor spec schema。
3. canonical examples 和测试向量。

本 repo 不再是 official pack 发布仓库，不保存真实业务 Factor pack、release manifest、checksum、SBOM、attestation 或 lab promotion 状态。`official` 在这里表示“官方稳定合约”，不是“所有可安装官方因子包的仓库”。

## 边界

| 属于本 repo | 不属于本 repo |
| --- | --- |
| `src/evozeus_factors_official/factor.py` | 真实业务 Factor pack |
| `schemas/official-factor-spec.schema.json` | pack release manifest |
| `examples/factors/` | checksum / SBOM / attestation |
| `examples/specs/` | lab reviewed / promotion queue |
| `tests/` | runtime install source |

## Official Contract

官方 Factor spec 比 lab 草案多三层约束：

- `stability` 必须是 `official`。
- `compatibility.evozeus_protocol` 必须声明协议范围。
- `governance.owner` 必须声明维护责任。

示例 Factor 仍然只是 canonical example，不代表默认安装的业务 Factor。

## 验证

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_official_factor_spec.py examples/specs/*.json
```

通过标准：

- `OfficialFactor` 不能被直接实例化。
- spec 必须声明 official stability、compatibility 和 governance owner。
- `matched` 结果必须带 `evidence_refs`。
- examples 必须是脱敏测试输入，不包含 private session。
