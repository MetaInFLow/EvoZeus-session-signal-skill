# evozeus-factors-official

`evozeus-factors-official` 是 EvoZeus Factor 的 **official contract repo**。

它只放三类东西：

1. 稳定 Python `OfficialFactor` 抽象类。
2. 官方 Factor spec schema。
3. official factors 和测试向量。

本 repo 不再是 official pack 发布仓库，不保存真实业务 Factor pack、release manifest、checksum、SBOM、attestation 或 lab promotion 状态。`official` 在这里表示“官方稳定合约”，不是“所有可安装官方因子包的仓库”。

## 边界

| 属于本 repo | 不属于本 repo |
| --- | --- |
| `src/evozeus_factors_official/factor.py` | 真实业务 Factor pack |
| `schemas/official-factor-spec.schema.json` | pack release manifest |
| `factors/<factor-slug>/` | checksum / SBOM / attestation |
| `tests/` | runtime install source |

## Official Contract

官方 Factor spec 比 lab 草案多三层约束：

- `stability` 必须是 `official`。
- `compatibility.evozeus_protocol` 必须声明协议范围。
- `governance.owner` 必须声明维护责任。
- `title_i18n` 必须声明 `zh-CN` / `en-US` 双语标题。
- `summary_i18n` 必须声明 `zh-CN` / `en-US` 双语功能说明。

Official Factor 仍然只是 official factor，不代表默认安装的业务 Factor。

## Official Factor Layout

官方 Factor全部平铺在 `factors/` 下。每个 factor 单元自带代码、spec 和脱敏输入：

```text
factors/
  repeated-request/
    factor.py
    spec.json
    session.json
  usage-sentence-cloud/
    factor.py
    spec.json
    session.json
  tool-failure-frequency/
    factor.py
    spec.json
    session.json
  key-sentence-trends/
    factor.py
    spec.json
    session.json
  task-completion/
    factor.py
    spec.json
    session.json
  user-input-sentiment/
    factor.py
    spec.json
    session.json
  session-resource-usage/
    factor.py
    spec.json
    session.json
```

当前 official factors 覆盖：

| Factor | 输入类型 | 输出结果 | 可视化输出 | 普通说明 |
| --- | --- | --- | --- | --- |
| `repeated-request` | `session` | `evidence_record_set` | `builtin.table.v1` | 识别用户是否重复提出同一个还没有解决的请求，并列出对应消息证据。 |
| `usage-sentence-cloud` | `session` / `project` / `scan_record_set` | `high_frequency_phrase_set` | `builtin.word_cloud.v1` | 找出用户会话里反复出现的常用表达，并用词云展示高频句子。 |
| `tool-failure-frequency` | `session` / `project` / `scan_record_set` | `frequency_distribution` | `builtin.bar_chart.v1` | 统计哪些工具调用失败最多，并用图表展示失败次数分布。 |
| `key-sentence-trends` | `session` / `project` / `scan_record_set` | `key_sentence_trend` | `builtin.line_chart.v1` / `builtin.heatmap.v1` | 按时间统计关键句出现趋势，帮助看出用户关注点如何变化。 |
| `task-completion` | `session` | `task_completion_verdict` | `builtin.table.v1` | 判断一次会话里的任务是否已经完成，并给出支撑这个判断的事件证据。 |
| `user-input-sentiment` | `session` / `project` / `scan_record_set` | `user_sentiment` / `frequency_distribution` | `builtin.bar_chart.v1` / `builtin.table.v1` | 判断用户在会话里表达的是正向、负向还是中性情绪，并保留对应用户消息作为证据。 |
| `session-resource-usage` | `session` / `project` / `scan_record_set` | `session_resource_usage` / `frequency_distribution` | `builtin.bar_chart.v1` / `builtin.table.v1` | 提取当前会话使用过的 tool、skill、MCP server、plugin 和 connector，并统计各自出现次数。 |

## Factor Input / Result / Visualization Contract

Official Factor 输入由 runtime materialize 为统一 envelope。输入可以是单个 session、project、scan record set、ledger query、历史 factor result set 或 mixed context。

Official Factor 输出统一为 `OfficialFactorResult`。结果包含：

- `target_type` / `target_id`：本次分析目标。
- `scores` / `statistics`：小型数值和聚合结果。
- `datasets`：可落账 read model，例如 high-frequency phrase set。
- `presentations`：可插拔前端组件的展示 contract，例如 `builtin.word_cloud.v1`。
- `evidence_refs`：指向 session event、scan record 或 prior factor result 的证据引用。

FactorResult 不携带前端代码。前端组件由 infra 的 visualization component registry 加载；组件不可用时必须 fallback 到 `builtin.table.v1` 或 `builtin.json.v1`。

新增 factor 的完整步骤见 [新建 Official Factor 指南](docs/guides/create-official-factor.md)。

## 验证

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_official_factor_spec.py factors/*/spec.json
```

通过标准：

- `OfficialFactor` 不能被直接实例化。
- spec 必须声明 official stability、compatibility、governance owner 和双语 metadata。
- `matched` 结果必须带 `evidence_refs`。
- test_vectors 必须是脱敏测试输入，不包含 private session。
