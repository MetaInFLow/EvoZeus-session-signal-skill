# Official Factor Visualization Contract Design

- Status: Accepted
- Date: 2026-06-19
- Owner: EvoZeus factor contract
- Language: 中文为主，保留必要 English contract 名称

## 背景

`EvoZeus-session-signal-skill` 当前只定义最小 Python `OfficialFactor` 抽象、official spec schema 和 official factors。随着 `EvoZeus-infra` 承接 scanner / runner / ledger / report，Factor 的输入和输出边界需要升级：

```text
Scanner / Ledger
  -> OfficialFactorInput
  -> OfficialFactor
  -> OfficialFactorResult
  -> Ledger
  -> Report / Dashboard / Drawer / TUI
```

Factor 输入不应固定为单个 `SessionEnvelope`。它可能是一个 session、一个 chat record、一个 project 下的多个 sessions、一组 scan records、全量 ledger query 结果、历史 factor results，或这些数据的组合。

Factor 输出也不应只包含 `matched / not_matched / error`。一些 Factor 会输出统计分析、聚合 read model、可视化建议和 drill-down 证据。例如 `moment-miner` 的高频使用句词云不是普通单词频率，而是一个业务 read model：

```text
usageSentenceCloud
  sentence_id
  display_sentence
  text
  value
  weight
  count
  raw_count
  session_count
  category
  sample_session_ids
```

前端 WordCloud 只是这个 read model 的一种 presentation：`wordField=text`、`weightField=value`、`colorField=category`。同一份 read model 还可以渲染成表格、趋势线、热力图或证据列表。

因此 official contract 要定义的是 **可落账 dataset + 可插拔 presentation contract**，而不是固定 chart enum。

## 目标

1. 定义稳定的 `OfficialFactorInput`，支持 session、project、scan record set、ledger query result、factor result set 和 mixed context。
2. 定义稳定的 `OfficialFactorResult`，包含 target、scores、statistics、datasets、presentations 和 evidence refs。
3. 让 Factor 可以声明“这组数据适合怎样展示”，但不携带前端代码。
4. 让前端 visualization component 通过 registry 可插拔加载。
5. 让 ledger 能保存 result、dataset、presentation 和 component reference，并支持 report / dashboard / drawer / TUI 消费。
6. 让 UI host 在组件不可用时可以 fallback 到 table 或 JSON。

## 非目标

1. 本 repo 不实现 React / Vue / ECharts / Ant Design Charts 组件。
2. 本 repo 不负责加载远程前端 bundle。
3. 本 repo 不定义真实业务 Factor pack 的发布、安装、checksum、SBOM 或 attestation。
4. 本 repo 不替代 `EvoZeus-infra` 的 ledger schema、route registry 或 permission gate。

## 核心抽象

### OfficialFactorInput

`OfficialFactorInput` 是 runner materialize 后传给 Factor 的统一输入 envelope。

```text
OfficialFactorInput
  schema_version
  input_kind
  target
  records
  prior_results
  context
```

`input_kind` 表示输入组合的主语义：

```text
session
chat_record
project
scan_record_set
ledger_query
factor_result
factor_result_set
mixed_context
```

`target` 表示本次分析的主要目标，不等于 evidence：

```text
target_type: session | event | task_span | project | scan_record_set | factor_result_set | case | custom
target_id: stable target id
provider: codex | claude_code | cursor | feishu | ...
project_key: optional project key
session_ids: optional session id list
```

`records` 保存被分析的数据，可以包含 `SessionEnvelope`、scan refs、ledger rows、history factor results 或 normalized artifacts。official contract 只要求每条 record 有 `record_type`、`record_id`、`payload` 和可选 `source_ref`，不把 provider 私有格式泄露给 Factor。

### OfficialFactorResult

`OfficialFactorResult` 是 Factor 唯一输出。它必须能被 ledger 拆成结构化结果、dataset、presentation、tag 和 evidence。

```text
OfficialFactorResult
  schema_version
  result_id
  factor_id
  version
  stage
  target_type
  target_id
  status
  confidence
  tags
  scores
  statistics
  datasets
  presentations
  evidence_refs
  verdict_signals
  notes
```

`status` 保持最小稳定状态：

```text
matched
not_matched
skipped
error
```

`scores` 保存可排序、可聚合的数值分数。`statistics` 保存小型聚合对象。大块列表或矩阵进入 `datasets`。

### ResultDataset

`ResultDataset` 是可落账 read model。它比 `statistics` 更结构化，服务 dashboard、report 和 drill-down。

```text
ResultDataset
  id
  semantic_type
  shape
  primary_key
  records
  schema
  evidence_policy
```

`semantic_type` 是业务语义，不是图表类型：

```text
high_frequency_phrase_set
time_series
distribution
relationship_flow
ranked_session_set
evidence_record_set
score_breakdown
custom:<namespace>/<name>.v1
```

`shape` 表示数据形态：

```text
record_set
time_series
matrix
tree
graph
scalar_set
```

结构片段：高频使用句 read model。

```json
{
  "id": "usage_sentence_cloud",
  "semantic_type": "high_frequency_phrase_set",
  "shape": "record_set",
  "primary_key": "sentence_id",
  "records": [
    {
      "sentence_id": "usage_sentence_7c63da598023",
      "display_sentence": "合理利用 subagent",
      "text": "合理利用 subagent",
      "value": 2.27227,
      "weight": 2.27227,
      "count": 24,
      "raw_count": 47,
      "session_count": 24,
      "category": "工作流句",
      "sample_session_ids": ["019d337c-b0e1-7cb2-9de5-9586e3e8953b"]
    }
  ],
  "schema": {
    "sentence_id": "string",
    "text": "string",
    "value": "number",
    "category": "string"
  }
}
```

### ResultPresentation

`ResultPresentation` 是可视化建议。它引用 dataset，并声明用哪个组件 contract 渲染。

```text
ResultPresentation
  id
  title
  component_ref
  data_ref
  bindings
  props
  routes
  fallback
  priority
```

结构片段：使用词云展示高频使用句。

```json
{
  "id": "usage_sentence_word_cloud",
  "title": "高频使用句云",
  "component_ref": "builtin.word_cloud.v1",
  "data_ref": "usage_sentence_cloud",
  "bindings": {
    "word": "text",
    "weight": "value",
    "color": "category"
  },
  "props": {
    "height": 420
  },
  "routes": ["dashboard", "drawer"],
  "fallback": ["builtin.table.v1", "builtin.json.v1"],
  "priority": 80
}
```

`component_ref` 允许三类值：

```text
builtin.word_cloud.v1
official.usage_sentence_cloud.v1
custom:moment-miner/usage-sentence-cloud.v1
```

official contract 不约束具体前端技术栈。React、Web Component、iframe sandbox 都由 UI host 和 visualization registry 决定。

## Visualization Component Registry

Visualization component 是独立注册的前端渲染能力，不属于 FactorResult 本体。

```text
VisualizationComponent
  component_id
  version
  runtime
  entrypoint
  export_name
  props_schema
  accepted_semantic_types
  required_bindings
  optional_bindings
  fallback_component
  trust_level
```

结构片段：

```json
{
  "component_id": "builtin.word_cloud",
  "version": "1.0.0",
  "runtime": "react",
  "entrypoint": "./dist/word-cloud.js",
  "export_name": "WordCloudRenderer",
  "props_schema": "./props.schema.json",
  "accepted_semantic_types": ["high_frequency_phrase_set"],
  "required_bindings": ["word", "weight"],
  "optional_bindings": ["color"],
  "fallback_component": "builtin.table.v1",
  "trust_level": "builtin"
}
```

UI host 加载流程：

```text
ResultPresentation
  -> resolve component_ref in registry
  -> check component version
  -> check dataset semantic_type
  -> check required bindings
  -> map dataset records into component props
  -> render component
  -> fallback when unavailable
```

组件只能接收 host 传入的 sanitized props，不直接读 ledger、不读本地文件、不联网、不访问 raw session。

## Ledger 映射

`EvoZeus-infra` 可以把 result 拆成这些层：

```text
factor_results
  result_id
  factor_id
  target_type
  target_id
  status
  confidence
  scores_json
  statistics_json

factor_result_datasets
  result_id
  dataset_id
  semantic_type
  shape
  primary_key
  schema_json
  records_json

factor_result_presentations
  result_id
  presentation_id
  component_ref
  data_ref
  bindings_json
  props_json
  fallback_json
  priority

factor_evidence
  result_id
  evidence_ref
```

现有 `factor_result_routes` 继续保留。`presentations.routes` 是 Factor 的展示建议；runtime route registry 可以接受、覆盖或禁用它。

## 安全边界

1. Factor 不输出前端代码，只输出 data 和 presentation descriptor。
2. 未知 component 必须经过 visualization registry 安装和校验。
3. community component 默认使用 sandboxed iframe 或 Web Component 隔离。
4. builtin / official component 可以用 host 可信加载路径。
5. component 不能直接访问 ledger、session 原文、filesystem、network 或 env。
6. evidence drill-down 只能通过 host 提供的受控 action。

## 最小内置组件

P0 内置组件建议：

```text
builtin.table.v1
builtin.json.v1
builtin.metric_card.v1
builtin.word_cloud.v1
builtin.line_chart.v1
builtin.heatmap.v1
builtin.evidence_list.v1
```

这组内置组件覆盖大多数 read model，且为 unknown presentation 提供 fallback。

## 验收标准

1. official contract 能表达 `moment-miner` 高频使用句 read model 和词云 presentation。
2. official contract 能表达纯表格、纯统计、趋势、热力、证据列表。
3. FactorResult 不包含前端代码。
4. presentation 组件不可用时可以 fallback。
5. ledger 能记录 datasets 和 presentations。
6. UI host 能通过 registry 解析 component_ref 并校验 bindings。
