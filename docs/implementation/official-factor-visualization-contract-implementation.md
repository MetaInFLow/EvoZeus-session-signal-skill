# Official Factor Visualization Contract Implementation

- Status: Implemented in repo contract surface
- Date: 2026-06-19
- Owner: EvoZeus factor contract
- Language: 中文为主，保留必要 English contract 名称

## 实现范围

本次实现把 `evozeus-session-signal-skill` 从“最小 session-only result contract”升级为“Session Signal SKILL repo”。它直接维护可运行的 official review factors，而不是维护独立演示目录。

当前 repo 范围：

- Python contract：`src/evozeus_session_signal_skill/factor.py`
- Spec schema：`schemas/official-factor-spec.schema.json`
- Official factors：`factors/<factor-slug>/`
- Contract / factor tests：`tests/`
- Spec validator：`scripts/validate_official_factor_spec.py`

仍然不属于本 repo：

- runtime scanner / runner / ledger implementation
- visualization component registry runtime
- pack release manifest、checksum、SBOM、attestation
- infra install source

## 文件结构

所有 official factors 平铺在 `factors/` 下，每个 factor 单元自包含代码、spec 和脱敏 test vector 输入。

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

`factor.py` 内保留同名 Python spec 常量，`spec.json` 是可被 validator 独立检查的 JSON spec。两者需要同步维护。

## Python Contract

`OfficialFactorInput` 是 runner materialize 后传入 factor 的统一输入 envelope：

- `schema_version`
- `input_kind`
- `target`
- `records`
- `prior_results`
- `context`

`OfficialFactorResult` 是 factor 唯一输出：

- `target_type` / `target_id` / `stage`
- `status` / `confidence`
- `tags`
- `scores`
- `statistics`
- `datasets`
- `presentations`
- `evidence_refs`
- `verdict_signals`
- `notes`

`OfficialFactor.build_result()` 是安全构造器。它负责：

- 限定 `status` 为 `matched`、`not_matched`、`skipped`、`error`
- 限定 `confidence` 到 `0.0..1.0`
- 将 dataset / presentation mapping 归一化为 dataclass
- 将 evidence ref 归一化为结构化 mapping
- 强制 `matched` result 必须带 `evidence_refs`

## Dataset Contract

`OfficialResultDataset` 表示可落账 read model。它不是图表类型，而是业务语义数据：

- `id`
- `semantic_type`
- `shape`
- `primary_key`
- `records`
- `schema`
- `evidence_policy`

已覆盖的 semantic types：

- `evidence_record_set`
- `high_frequency_phrase_set`
- `frequency_distribution`
- `key_sentence_trend`

## Presentation Contract

`OfficialResultPresentation` 表示展示建议，只引用 dataset 和 visualization component ref，不携带前端代码：

- `id`
- `title`
- `component_ref`
- `data_ref`
- `bindings`
- `props`
- `routes`
- `fallback`
- `priority`

当前 official factors 使用的 component refs：

- `builtin.table.v1`
- `builtin.json.v1`
- `builtin.word_cloud.v1`
- `builtin.bar_chart.v1`
- `builtin.line_chart.v1`
- `builtin.heatmap.v1`

组件可插拔机制由 infra/UI host 实现：host 根据 `component_ref` 在 visualization component registry 中解析组件，校验 dataset semantic type 和 bindings，再把 sanitized props 传给组件。无法解析时按 `fallback` 渲染为 table 或 JSON。

## Spec Schema

`schemas/official-factor-spec.schema.json` 已要求 official factor spec 声明：

- `stability = official`
- `title_i18n.zh-CN`
- `title_i18n.en-US`
- `summary_i18n.zh-CN`
- `summary_i18n.en-US`
- `compatibility.evozeus_protocol`
- `governance.owner`
- `input_contract.accepted_input_kinds`
- `input_contract.target_types`
- `input_contract.record_types`
- `output_contract.dataset_semantic_types`
- `output_contract.presentation_components`
- `test_vectors`

Python validator 也检查同一组关键字段，供没有 JSON schema runtime 的环境使用。

## 已实现 Session Signal Factors

`repeated-request`

- 输入：single session
- 输出：`evidence_record_set`
- 展示：`builtin.table.v1`
- 作用：识别用户重复发起同一未完成请求，并落证据行。

`usage-sentence-cloud`

- 输入：single session / project / scan record set
- 输出：`high_frequency_phrase_set`
- 展示：`builtin.word_cloud.v1`
- 作用：把 moment-miner 高频使用句机制沉淀为 official factor read model，词云只是其中一个 presentation。

`tool-failure-frequency`

- 输入：single session / project / scan record set
- 输出：`frequency_distribution`
- 展示：`builtin.bar_chart.v1`
- 作用：统计工具失败事件在不同 tool 上的分布。

`key-sentence-trends`

- 输入：single session / project / scan record set
- 输出：`key_sentence_trend`
- 展示：`builtin.line_chart.v1`、`builtin.heatmap.v1`
- 作用：按时间桶聚合关键句 cluster 的趋势。

`task-completion`

- 输入：single session
- 输出：`task_completion_verdict`
- 展示：`builtin.table.v1`
- 作用：判断一次会话里的任务是否已经完成，并给出支撑这个判断的事件证据。

`user-input-sentiment`

- 输入：single session / project / scan record set
- 输出：`user_sentiment`、`frequency_distribution`
- 展示：`builtin.bar_chart.v1`、`builtin.table.v1`
- 作用：判断用户在会话里表达的是正向、负向还是中性情绪。

`session-resource-usage`

- 输入：single session / project / scan record set
- 输出：`session_resource_usage`、`frequency_distribution`
- 展示：`builtin.bar_chart.v1`、`builtin.table.v1`
- 作用：提取当前 session 使用过的 tool、skill、MCP server、plugin 和 connector。

## 验证方式

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_official_factor_spec.py factors/*/spec.json
```

验收点：

- contract dataclass 能稳定序列化 input、result、dataset、presentation
- `matched` result 没有 evidence refs 时会被拒绝
- 所有 official factor spec 通过 validator
- 所有 `factors/<factor-slug>/session.json` 都是脱敏 test vector 输入
- official factors 输出的 `datasets` 和 `presentations` 能表达 moment-miner 高频词云、频率分布、趋势线、热力图和证据表
