# 新建 Official Factor 指南

本指南用于在 `EvoZeus-session-signal-skill` 中新增一个 official factor。这里的 official 当前定位为“当下识别需要被总结成 SKILL 的 sessions 的官方信号方法”：factor 是对聊天记录进行分析的组件，顶层 `SKILL.md` 是利用 factor 结果判断是否值得沉淀成 SKILL、得出结论和确定呈现形式的方法层。

这里的 official 不是业务 pack 的发布入口，也不是最终评分模型。新增 factor 必须说明它如何帮助判断 session 是否值得总结成 SKILL，以及它如何暴露好案例、风险、阻塞、用户不满、重复返工、工具失败、资源使用或关键产出。

## Official Skill 和 Factor 的关系

新增 factor 前先区分两件事：

| 层级 | 责任 | 产物 |
| --- | --- | --- |
| Factor | 分析聊天记录，抽取一个稳定信号。 | `FACTOR.xml`、`factor.py`、dataset、tag、score、evidence refs、presentation contract。 |
| `SKILL.md` | 组合多个 factor 的结果，形成 SKILL 候选结论和展示方案。 | 候选标签、推荐沉淀形式、判断依据、置信度、可视化布局和解释规则。 |

因此，一个 official factor 不能只回答“我能抽什么数据”，还要回答：

- 它支持哪个 SKILL-candidate dimension；字段名仍沿用 `quality_dimension`，避免破坏现有一级对象和契约。
- 它的信号在什么情况下能支撑“总结成 SKILL”的结论。
- 它的信号在什么情况下只能作为 diagnostic。
- 它需要如何在 Global Canvas、Session Detail 或筛选器里呈现。
- 它需要什么 evidence refs，才能让结论可追溯到具体 chat/event。

## 先判断是否应该放在本 repo

只在满足下面条件时从本 repo 新建 factor：

- 它要沉淀为稳定的 `OfficialFactor` contract 示例。
- 它会影响官方 factor spec schema、Python contract 或官方测试向量。
- 它不依赖真实业务私有数据、私有 pack release、checksum、SBOM 或 attestation。

如果是业务场景 factor、客户定制 factor、promotion candidate 或 runtime install source，应放到 infra / business factor pack，而不是本 repo。

## 最小目录结构

每个 factor 一个独立目录，目录名使用 kebab-case：

```text
factors/<factor-slug>/
  FACTOR.xml
  factor.py
  spec.json
  session.json
```

- `FACTOR.xml`：该 factor 的一等声明文件，描述 metadata、输入 channel、输出 dataset、presentation、依赖、证据策略和质量说明。
- `factor.py`：可运行 Python factor，实现 `OfficialFactor.evaluate()`。
- `spec.json`：兼容 legacy validator 的官方 spec；当前仍需和 `FACTOR.xml` / Python spec 保持同步。
- `session.json`：脱敏 test vector 输入，不能包含 private session 或客户数据。

`factor.py` 中的 Python spec 常量必须和 `FACTOR.xml`、`spec.json` 保持同步。

## 命名规则

- 目录名：`task-completion`、`user-input-sentiment` 这种 kebab-case。
- `factor_id`：使用 `official.<factor-slug>`，例如 `official.task-completion`。
- Python class：使用 PascalCase 并以 `Factor` 结尾，例如 `TaskCompletionFactor`。
- Python spec 常量：使用大写 snake case，例如 `OFFICIAL_TASK_COMPLETION_SPEC`。
- dataset id / presentation id：使用 snake_case，例如 `task_completion_verdict`。

## Factor 类型分类

新建 factor 前必须先定义五个维度：`quality_dimension`、`input_scope`、`target_scope`、`stage` 和 `write_surface`。这五个维度决定 factor 对“是否值得沉淀成 SKILL”的判断有什么贡献、应该吃什么输入、给谁打结果、处在哪个处理阶段，以及结果应该写到哪里。

### 0. quality_dimension：SKILL 候选判断维度

`quality_dimension` 是保留的契约字段名，决定这个 factor 会被 `SKILL.md` 如何用于 SKILL 候选结论和呈现。一个 factor 可以覆盖多个维度，但必须声明主维度。

| 维度 | 典型问题 | 推荐输出 |
| --- | --- | --- |
| `user_satisfaction` | 用户是否满意、纠错、报告问题或表达不满？ | event tag、session tag、sentiment dataset、dissatisfaction evidence。 |
| `task_closure` | 任务是否完成、阻塞、未完成或未知？ | session verdict、confidence、completion evidence。 |
| `rework_pressure` | 用户是否重复提出同一未解决请求？ | repeated chain dataset、event refs、session tag。 |
| `tool_reliability` | 工具失败是否拖累完成质量？ | failure distribution、sample table、tool/event refs。 |
| `resource_correctness` | tool、skill、MCP server 是否被真实使用并支撑任务？ | resource usage dataset、verified/diagnostic split。 |
| `intent_output_density` | 会话是否有清晰行动、对象、否定、产出和交付句？ | key sentence trend、role-segmented dataset。 |
| `communication_pattern` | 用户和 assistant 的高频表达是否暴露偏好或系统性模式？ | phrase frequency dataset、role-segmented presentation。 |

定义原则：

- 能直接影响 SKILL 候选结论的信号，要说明它支持哪些 label，例如 `success_skill_candidate`、`problem_skill_candidate`、`failure_skill_candidate`、`repeat_skill_candidate`、`workflow_skill_candidate`、`not_skill_candidate`。
- 只能解释上下文的信号，要标为 diagnostic，不要伪装成 SKILL-candidate verdict。
- 每个 factor 的 `FACTOR.xml/quality_notes` 必须说明已知误判和不应该如何解读。
- 如果新增 factor 改变 SKILL 候选判断规则，必须同步更新顶层 `SKILL.md`。

### 1. input_scope：输入范围

`input_scope` 对应 `input_contract.accepted_input_kinds` 和 `record_types`。

| 类型 | 适用场景 | 推荐 contract |
| --- | --- | --- |
| `event` | 只分析一条聊天记录、tool result 或 assistant result。 | `accepted_input_kinds=["event"]`，`record_types=["session_event"]`。当前 runtime 仍以 `session` 输入为主，event-level factor 可先用 `session` 输入并在内部过滤 event。 |
| `session` | 分析一整个会话，例如任务是否完成、会话里用了哪些资源。 | `accepted_input_kinds=["session"]`，`record_types=["session_envelope"]`。 |
| `record_set` | 输入一批 user input、多个 session 或 scan 结果做聚合，例如高频句、趋势、分布。 | `accepted_input_kinds=["project", "scan_record_set"]`，`record_types=["session_envelope", "user_input_record"]`。 |
| `prior_factor_result_set` | 不直接分析原始聊天，而是消费上游 factor 输出，例如基于情绪分类结果再做 AI 判断。 | `accepted_input_kinds=["factor_result_set"]`，`record_types=["factor_result"]`，`prior_result_policy="required"`。当前 runtime 需要后续补 prior results 输入。 |

### 2. target_scope：分析目标

`target_scope` 对应 `input_contract.target_types`，以及运行结果里的 `target_type` / `target_id`。

| 类型 | 什么时候用 | 输出目标示例 |
| --- | --- | --- |
| `event` | 结果要贴到某条 user input、assistant result 或 tool event 上。 | `target_type="event"`，`target_id="<event-id>"`。 |
| `session` | 结果描述整个会话。 | `target_type="session"`，`target_id="<session-id>"`。 |
| `project` | 结果描述一个项目、repo、客户空间或长期上下文。 | `target_type="project"`，`target_id="<project-key>"`。 |
| `scan_record_set` | 结果描述一次扫描得到的一批记录。 | `target_type="scan_record_set"`，`target_id="<scan-id-or-batch-id>"`。 |
| `factor_result_set` | 结果描述一组上游 factor 结果。 | `target_type="factor_result_set"`，`target_id="<result-set-id>"`。 |
| `case` | 结果形成一个需要后续处理的 case。 | `target_type="case"`，`target_id="<case-id>"`。 |

选择原则：

- 如果结果要跟在某条聊天记录后面展示，用 `target_scope=event`，即使 factor 为了上下文读取了整个 session。
- 如果结果是整段会话的判断，用 `target_scope=session`。
- 如果结果需要跨 session 统计，不要伪装成 session factor；应使用 `project` 或 `scan_record_set`。
- 如果结果依赖其他 factor 的输出，应使用 `prior_factor_result_set` 输入，不要重复实现上游逻辑。

### 3. stage：处理阶段

`stage` 对应 `FactorStage`，用于表达 factor 在流水线里的职责。

| Stage | 职责 | 典型输出 |
| --- | --- | --- |
| `normalize` | 把原始事件、文本或工具结果转成规范化片段。 | span、resource mention、canonical record。 |
| `signal_extraction` | 从输入中抽取可直接打标签的信号。 | event tag、session tag、evidence row。 |
| `insight_aggregation` | 对一批信号或记录做聚合，生成趋势、频率、分布。 | dataset、trend、word cloud。 |
| `verdict_building` | 基于信号或聚合结果形成判断。 | verdict、session tag、confidence、reason。 |
| `case_building` | 把判断升级成待处理 case 或行动建议。 | case record、comment、next action。 |

### 4. write_surface：结果写入表面

`write_surface` 不是当前 spec 的独立字段，但必须在 `output_contract.fields`、`datasets`、`tags`、`verdict_signals` 和 `presentations` 中体现。

| 类型 | 用法 | 当前承载方式 |
| --- | --- | --- |
| `event_tag` | 给某条 event 打标签，例如 `user_sentiment=negative`。 | `tags` + 指向 event 的 `evidence_refs`。runtime 会展开到 `event_factor_tags`。 |
| `session_tag` | 给整个 session 打标签，例如 `user_dissatisfied=true`。 | `tags`，`target_type="session"`。 |
| `event_annotation` | 给某条 assistant result 或 tool result 附加结构化说明。 | `datasets` 记录 `event_id`，并用 `evidence_refs` 指向 event。 |
| `dataset` | 生成可查询、可展示的结构化 read model。 | `datasets`。 |
| `presentation` | 建议前端如何展示 dataset。 | `presentations`。 |
| `comment` | 生成解释性备注、AI 分析或 reviewer note。 | 当前没有一等 `comment` 字段，应先用 `datasets` 的 comment record 或 `verdict_signals` 表达，后续 runtime 可升级为独立表。 |

### 典型场景映射

| 场景 | 类型归属 | 推荐 factor 形态 | 当前状态 |
| --- | --- | --- | --- |
| 单条 user input 进来，分析情绪分类并打标签。 | `input_scope=event`，`target_scope=event`，`stage=signal_extraction`，`write_surface=event_tag`。 | `official.user-input-sentiment` 应拆出 event-level 语义；session 汇总可以作为另一个 aggregation 输出。 | 现有实现以 session 输入返回 session result，event tag 依赖 `evidence_refs` 间接展开。 |
| 输入一堆 user input，分析高频说法。 | `input_scope=record_set`，`target_scope=scan_record_set/project`，`stage=insight_aggregation`，`write_surface=dataset/presentation`。 | `official.usage-sentence-cloud`。 | 现有 contract 声明支持批量，但 runtime 仍主要按 session 跑，需要真正 batch runner 支持。 |
| 一个 session 进来，提取用了什么 skill，并放到提到 skill 的 AI result 后面。 | `input_scope=session`，`target_scope=event`，`stage=signal_extraction` 或 `normalize`，`write_surface=event_annotation`。 | 可以从 `official.session-resource-usage` 拆出 `session-resource-mention`，每条记录包含 `assistant_event_id` 和 `resource_name`。 | 现有实现更偏 session-level 资源统计，event-level annotation 还不够精确。 |
| 对用户情感分类结果再做 AI 分析，发现用户不满意，给 session 打标签或 comment。 | `input_scope=prior_factor_result_set`，`target_scope=session`，`stage=verdict_building` 或 `case_building`，`write_surface=session_tag/comment`。 | 新建 meta-factor，例如 `official.user-dissatisfaction-verdict`，依赖 `official.user-input-sentiment`。 | 当前 runtime 没有 prior factor results 输入，需后续补 context 和存储支持。 |

### 场景实例模板

下面示例不是完整 spec，只展示新建 factor 时最容易混淆的契约、target 和输出形态。当前 runtime 仍是 session-centric；如果 ideal contract 暂时不能落地，应在实现里保留 event id、batch id 或 prior result id，方便后续迁移。

#### 示例 A：单条 user input 情绪打标签

场景：用户说“不是这样，改动太大了”，需要给这条 user event 打 `user_sentiment=negative` 标签。

实例 factor：`official.user-input-sentiment-event`

类型定义：

```text
input_scope: event
target_scope: event
stage: signal_extraction
write_surface: event_tag
```

推荐 contract：

```json
{
  "input_contract": {
    "event_model": "SessionEvent",
    "required_fields": ["event.id", "event.role", "event.text"],
    "accepted_input_kinds": ["event"],
    "target_types": ["event"],
    "record_types": ["session_event"],
    "prior_result_policy": "not_required"
  },
  "output_contract": {
    "fields": ["tags", "scores", "datasets", "evidence_refs"],
    "dataset_semantic_types": ["user_sentiment"],
    "presentation_components": ["builtin.table.v1", "builtin.json.v1"]
  }
}
```

当前 runtime 兼容写法：

```json
{
  "input_contract": {
    "event_model": "SessionEvent[]",
    "required_fields": ["events[].id", "events[].role", "events[].text"],
    "accepted_input_kinds": ["session"],
    "target_types": ["event"],
    "record_types": ["session_envelope"],
    "prior_result_policy": "not_required"
  }
}
```

结果形态：

```json
{
  "target_type": "event",
  "target_id": "user-17",
  "tags": [{"type": "user_sentiment", "value": "negative"}],
  "scores": {"sentiment_score": -0.8},
  "evidence_refs": [{"ref_id": "user-17", "kind": "user_turn"}]
}
```

#### 示例 B：一批 user input 高频说法

场景：输入 500 条 user input，统计用户最常说的短句，例如“不要改文件”“只读审查”“输出具体路径”。

实例 factor：`official.usage-sentence-cloud`

类型定义：

```text
input_scope: record_set
target_scope: scan_record_set
stage: insight_aggregation
write_surface: dataset/presentation
```

推荐 contract：

```json
{
  "input_contract": {
    "event_model": "UserInputRecord[]",
    "required_fields": ["records[].id", "records[].text", "records[].session_id"],
    "accepted_input_kinds": ["scan_record_set", "project"],
    "target_types": ["scan_record_set", "project"],
    "record_types": ["user_input_record", "session_envelope"],
    "prior_result_policy": "not_required"
  },
  "output_contract": {
    "fields": ["scores", "datasets", "presentations", "evidence_refs"],
    "dataset_semantic_types": ["high_frequency_phrase_set"],
    "presentation_components": ["builtin.word_cloud.v1", "builtin.table.v1", "builtin.json.v1"]
  }
}
```

结果形态：

```json
{
  "target_type": "scan_record_set",
  "target_id": "scan-2026-06-20-codex-user-inputs",
  "datasets": [
    {
      "id": "usage_sentence_cloud",
      "semantic_type": "high_frequency_phrase_set",
      "records": [
        {
          "sentence_id": "usage_sentence_a1b2",
          "text": "不要改文件",
          "count": 37,
          "session_count": 29,
          "sample_session_ids": ["s1", "s2"]
        }
      ]
    }
  ],
  "presentations": [
    {
      "component_ref": "builtin.word_cloud.v1",
      "data_ref": "usage_sentence_cloud",
      "bindings": {"word": "text", "weight": "count"}
    }
  ]
}
```

#### 示例 C：把 skill mention 贴到 AI result 后面

场景：assistant 消息里说“我会用 systematic-debugging 排查”，需要在这条 assistant event 后面展示提到的 skill。

实例 factor：`official.session-resource-mention`

类型定义：

```text
input_scope: session
target_scope: event
stage: signal_extraction
write_surface: event_annotation
```

推荐 contract：

```json
{
  "input_contract": {
    "event_model": "SessionEvent[]",
    "required_fields": ["events[].id", "events[].role", "events[].text"],
    "accepted_input_kinds": ["session"],
    "target_types": ["event"],
    "record_types": ["session_envelope"],
    "prior_result_policy": "not_required"
  },
  "output_contract": {
    "fields": ["datasets", "presentations", "evidence_refs"],
    "dataset_semantic_types": ["session_resource_mention"],
    "presentation_components": ["builtin.table.v1", "builtin.json.v1"]
  }
}
```

结果形态：

```json
{
  "target_type": "event",
  "target_id": "assistant-9",
  "datasets": [
    {
      "id": "session_resource_mentions",
      "semantic_type": "session_resource_mention",
      "primary_key": "event_id,resource_type,resource_name",
      "records": [
        {
          "event_id": "assistant-9",
          "resource_type": "skill",
          "resource_name": "systematic-debugging",
          "mention_text": "systematic-debugging"
        }
      ]
    }
  ],
  "evidence_refs": [{"ref_id": "assistant-9", "kind": "assistant_turn"}]
}
```

注意：如果一个 result 同时包含多个 event 和多个 resource，不要只用顶层 `tags` 表达，否则 `event_factor_tags` 展开时容易把所有 tag 交叉挂到所有 evidence event。应该在 dataset record 中保留 `event_id` 和 `resource_name` 的一一对应。

#### 示例 D：基于上游情绪结果做不满意判断

场景：`official.user-input-sentiment` 已经给多条 user input 标成 negative，新的 factor 再综合判断“这个 session 用户不满意”，并给 session 打标签或生成 comment。

实例 factor：`official.user-dissatisfaction-verdict`

类型定义：

```text
input_scope: prior_factor_result_set
target_scope: session
stage: verdict_building
write_surface: session_tag/comment
```

推荐 contract：

```json
{
  "input_contract": {
    "event_model": "FactorResult[]",
    "required_fields": ["prior_results[].factor_id", "prior_results[].target_id", "prior_results[].tags"],
    "accepted_input_kinds": ["factor_result_set"],
    "target_types": ["session"],
    "record_types": ["factor_result"],
    "prior_result_policy": "required"
  },
  "output_contract": {
    "fields": ["tags", "scores", "datasets", "verdict_signals", "evidence_refs"],
    "dataset_semantic_types": ["session_verdict_comment"],
    "presentation_components": ["builtin.table.v1", "builtin.json.v1"]
  }
}
```

结果形态：

```json
{
  "target_type": "session",
  "target_id": "session-42",
  "tags": [{"type": "user_dissatisfaction", "value": "detected"}],
  "scores": {"dissatisfaction_score": 0.86},
  "verdict_signals": ["user dissatisfaction detected from repeated negative sentiment"],
  "datasets": [
    {
      "id": "session_verdict_comments",
      "semantic_type": "session_verdict_comment",
      "records": [
        {
          "comment_id": "comment-1",
          "comment_type": "ai_analysis",
          "text": "用户多次表达不满意，建议后续优先确认需求边界。",
          "source_factor_ids": ["official.user-input-sentiment"]
        }
      ]
    }
  ],
  "evidence_refs": [
    {"ref_id": "user-17", "kind": "user_turn"},
    {"ref_id": "frun_sentiment_1", "kind": "factor_result"}
  ]
}
```

注意：当前 runtime 还没有一等 `prior_results` 输入和 `comment` 表；official guide 可以先定义 contract，runtime 实现前应使用 dataset comment record 作为兼容表达。

## Spec 必填要素

`spec.json` 必须通过 `schemas/official-factor-spec.schema.json`。核心字段如下：

| 字段 | 作用 |
| --- | --- |
| `schema_version` | 当前使用 `official.factor.v0`。 |
| `stability` | 必须是 `official`。 |
| `factor_id` | 稳定 ID，例如 `official.task-completion`。 |
| `version` | SemVer，例如 `v0.1.0`。 |
| `title` / `summary` | 默认展示标题和说明。 |
| `title_i18n` / `summary_i18n` | 双语 metadata，必须包含 `zh-CN` 和 `en-US`。 |
| `compatibility.evozeus_protocol` | 支持的 EvoZeus protocol 范围。 |
| `governance.owner` | 维护责任人。 |
| `input_contract` | 声明输入类型、目标类型和必需字段。 |
| `evidence_contract` | 声明 evidence ref 格式和隐私约束。 |
| `output_contract` | 声明 status、输出字段、dataset semantic type 和 presentation component。 |
| `test_vectors` | 指向脱敏测试输入和预期 status。 |

最小 spec 示例：

```json
{
  "schema_version": "official.factor.v0",
  "stability": "official",
  "factor_id": "official.example-signal",
  "version": "v0.1.0",
  "title": "Example signal",
  "summary": "识别会话里是否出现示例信号，并返回对应证据。",
  "title_i18n": {
    "zh-CN": "示例信号",
    "en-US": "Example signal"
  },
  "summary_i18n": {
    "zh-CN": "识别会话里是否出现示例信号，并返回对应证据。",
    "en-US": "Detects whether an example signal appears in a session and returns evidence."
  },
  "compatibility": {
    "evozeus_protocol": ">=0.1.0"
  },
  "governance": {
    "owner": "evozeus-factor-maintainers"
  },
  "input_contract": {
    "event_model": "SessionEvent[]",
    "required_fields": ["events[].id", "events[].role", "events[].text"],
    "accepted_input_kinds": ["session"],
    "target_types": ["session"],
    "record_types": ["session_envelope"],
    "prior_result_policy": "not_required"
  },
  "evidence_contract": {
    "ref_format": "event:<event-id>",
    "privacy": "Official factors must use redacted events and stable evidence refs."
  },
  "output_contract": {
    "statuses": ["matched", "not_matched", "skipped", "error"],
    "fields": ["scores", "datasets", "presentations", "evidence_refs"],
    "dataset_semantic_types": ["example_signal"],
    "presentation_components": ["builtin.table.v1", "builtin.json.v1"]
  },
  "test_vectors": [
    {
      "name": "example signal appears",
      "input": "factors/example-signal/session.json",
      "expected_status": "matched"
    }
  ]
}
```

## 输入契约设计

先按“Factor 类型分类”明确 factor 要分析什么对象，再决定输入范围：

- 只分析单条记录：优先设计为 `target_type="event"`；当前 runtime 未完全支持 event input 时，可暂用 `accepted_input_kinds=["session"]`，但必须在 dataset 和 evidence 中保留 `event_id`。
- 只分析单次对话：`accepted_input_kinds = ["session"]`，`target_types = ["session"]`。
- 需要跨会话聚合：使用 `accepted_input_kinds = ["project", "scan_record_set"]`，`target_types = ["project", "scan_record_set"]`。
- 依赖历史 factor 结果：使用 `accepted_input_kinds = ["factor_result_set"]`，并在 `prior_result_policy` 中声明 `required` 或 `optional`。

常见字段：

- `events[].id`：用于 evidence ref。
- `events[].role`：区分 user / assistant / tool / system。
- `events[].text`：用于文本信号识别。
- `events[].timestamp`：用于趋势、时间桶或 session timeline。
- `events[].tool_name`：用于 tool 使用和失败统计。

## 输出契约设计

Factor 输出统一使用 `OfficialFactorResult`。设计输出时先区分写入表面和三层 read model：

- `scores` / `statistics`：小型数值和摘要，适合快速判断。
- `datasets`：结构化 read model，适合落账、查询和可视化。
- `presentations`：展示建议，只引用 component ref，不携带前端代码。
- `tags`：标签型输出，适合 `event_tag` 或 `session_tag`。
- `verdict_signals`：判断型输出，适合 verdict/case 后续消费。
- `evidence_refs`：证据引用，必须能回到 event、scan record 或 prior factor result。

常用 `dataset_semantic_types`：

- `evidence_record_set`：证据行列表。
- `frequency_distribution`：频率分布。
- `key_sentence_trend`：关键句趋势。
- `task_completion_verdict`：任务完成判断。
- `user_sentiment`：用户情感判断。
- `session_resource_usage`：会话资源使用情况。

常用 `presentation_components`：

- `builtin.table.v1`
- `builtin.json.v1`
- `builtin.bar_chart.v1`
- `builtin.word_cloud.v1`
- `builtin.line_chart.v1`
- `builtin.heatmap.v1`

未知或高级组件不可直接写前端代码进 result；应通过 visualization registry 解决，并提供 `fallback`。

## Python 实现骨架

```python
from __future__ import annotations

from typing import Any, Mapping

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult


OFFICIAL_EXAMPLE_SIGNAL_SPEC = {
    "...": "和 spec.json 保持同步"
}


class ExampleSignalFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_EXAMPLE_SIGNAL_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        matched_event = next(
            (
                event
                for event in context.get("events", [])
                if event.get("role") == "user" and "example" in str(event.get("text", "")).lower()
            ),
            None,
        )

        if matched_event is None:
            return self.build_result(
                status="not_matched",
                target_type="session",
                target_id=session_id,
            )

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.7,
            scores={"example_signal_count": 1.0},
            datasets=[
                {
                    "id": "example_signals",
                    "semantic_type": "example_signal",
                    "shape": "record_set",
                    "primary_key": "event_id",
                    "records": [
                        {
                            "event_id": str(matched_event["id"]),
                            "signal": "example signal appeared",
                        }
                    ],
                    "schema": {
                        "event_id": "string",
                        "signal": "string",
                    },
                }
            ],
            presentations=[
                {
                    "id": "example_signal_table",
                    "title": "示例信号",
                    "component_ref": "builtin.table.v1",
                    "data_ref": "example_signals",
                    "bindings": {"row_key": "event_id"},
                    "fallback": ["builtin.json.v1"],
                }
            ],
            evidence_refs=[{"ref_id": str(matched_event["id"]), "kind": "user_turn"}],
        )
```

关键规则：

- `evaluate()` 只返回 `OfficialFactorResult`。
- `matched` 必须提供 `evidence_refs`。
- `confidence` 必须能解释，不要随意写满分。
- `datasets[].records` 必须是脱敏后的结构化数据。
- `presentations` 只描述展示方式，不包含前端实现。

## Test Vector

`session.json` 应该尽量小，只覆盖 factor 核心判断路径：

```json
{
  "session_id": "official-factor-session-example-signal",
  "events": [
    {
      "id": "user-1",
      "role": "user",
      "text": "Please check this example signal."
    }
  ]
}
```

避免：

- 真实用户姓名、客户名、账号、token、URL secret。
- 大段原始日志。
- 和 factor 判断无关的上下文。

## 测试要求

在 `tests/test_official_factors.py` 中加载新 factor，并至少断言：

- `result.status`
- `datasets[0].semantic_type`
- `presentations[0].component_ref`
- `evidence_refs`
- 关键 `scores` 或 `statistics`

如果改了 spec schema 或 Python validator，还要在 `tests/test_official_factor_contract.py` 中补 contract 测试。

## 验证命令

每次新增或修改 factor 后运行：

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_official_factor_spec.py factors/*/spec.json
```

如果环境有 `jsonschema`，也建议跑 JSON Schema 实体验证：

```bash
python3 - <<'PY'
import json
from pathlib import Path
import jsonschema

schema = json.loads(Path("schemas/official-factor-spec.schema.json").read_text(encoding="utf-8"))
validator = jsonschema.Draft202012Validator(schema)

for path in sorted(Path("factors").glob("*/spec.json")):
    validator.validate(json.loads(path.read_text(encoding="utf-8")))
print("json schema validation passed")
PY
```

## 提交前检查清单

- [ ] factor 目录名、`factor_id`、Python class 名称一致。
- [ ] `FACTOR.xml` 是该 factor 的一等声明文件，metadata、input channel、dataset、presentation、dependencies、evidence policy 和 quality notes 完整。
- [ ] `factor.py` 中的 spec 常量和 `FACTOR.xml` / `spec.json` 同步。
- [ ] 已明确 `quality_dimension`、`input_scope`、`target_scope`、`stage`、`write_surface`，且和 `FACTOR.xml` / `input_contract` / `output_contract` 一致。
- [ ] 已说明该 factor 对“识别是否值得沉淀成 SKILL”的贡献，以及哪些信号只能作为 diagnostic。
- [ ] 如该 factor 改变 SKILL 候选结论或呈现方式，已同步更新顶层 `SKILL.md`。
- [ ] `title_i18n` / `summary_i18n` 同时包含 `zh-CN` 和 `en-US`。
- [ ] `input_contract` 明确 accepted input kinds、target types、record types。
- [ ] `output_contract` 明确 dataset semantic types 和 presentation components。
- [ ] `matched` 分支返回稳定 `evidence_refs`。
- [ ] `session.json` 是脱敏 test vector。
- [ ] 单元测试覆盖 status、dataset、presentation、evidence。
- [ ] `python3 -m unittest discover -s tests` 通过。
- [ ] `python3 scripts/validate_official_factor_spec.py factors/*/spec.json` 通过。

## 常见错误

- 只写 `factor.py`，忘记同步 `FACTOR.xml`、`spec.json` 和顶层 `SKILL.md`。
- 只抽取数据，没有说明它如何被用于 SKILL 候选结论和呈现。
- 把 diagnostic signal 当成最终 SKILL-candidate verdict。
- 只写中文 `summary`，漏掉 `summary_i18n.en-US`。
- `matched` 没有 `evidence_refs`，会被 `build_result()` 拦截。
- dataset 直接按图表命名，例如 `bar_chart_data`，没有表达业务语义。
- presentation 引用了不存在的 `data_ref`。
- 把前端组件代码、业务 pack 发布信息或真实业务数据放进本 repo。
