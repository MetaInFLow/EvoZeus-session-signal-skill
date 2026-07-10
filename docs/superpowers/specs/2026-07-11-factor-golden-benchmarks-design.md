# EvoZeus Factor Golden Benchmarks 设计

- Status: 待用户确认
- Date: 2026-07-11
- Owner: EvoZeus factor maintainers
- Scope: `evozeus-session-signal-skill` official factors 与 `evozeus-infra` 消费边界

## 1. 目标

建立一套人工确认、可执行、可追溯的 Golden Benchmarks，作为 Factor 算法迭代时的标准答案。

Golden Benchmark 回答的是“对这组 session events，正确的 Factor 结果应该是什么”。算法实现只能向 Golden 答案收敛，不能根据当前算法输出自动更新答案。

本次同时完成两项 Factor 收敛：

1. 删除 `official.mbti-personality-profile`。MBTI 改由 Session Signal SKILL 综合多个 Factor 结果后生成，不再作为单一关键词 Factor。
2. 删除 `official.usage-sentence-cloud`。新增 `official.semantic-phrase-clusters`，用语义短句聚类替代精确字符串句云。

## 2. 成功标准

完成后应满足：

1. 每个保留的 official Factor 至少有 3 个 Golden Cases，覆盖正例、反例和关键边界。
2. Golden Cases 来源于真实历史中出现过的问题类型，但内容必须脱敏、缩短并移除客户名、账号、绝对路径和私有业务细节。
3. 每个 Case 同时声明期望答案和禁止答案，防止算法只命中正例却继续制造误判。
4. Golden evaluator 能运行全部 Factor，逐案例输出 `PASS` / `FAIL` 和字段级差异。
5. 离散语义字段精确匹配；浮点字段使用显式 tolerance；记录集合按稳定业务键比较，不依赖数组顺序。
6. `mbti-personality-profile` 和 `usage-sentence-cloud` 不再出现在 factor 目录、official factor 集合、runtime bridge 结果或报告 Factor 列表中。
7. 新的 `semantic-phrase-clusters` 能通过启动项目同义表达聚类案例，并通过报告对象隔离反例。

## 3. 方案选择

采用“语义答案 + 禁止答案 + 指标门槛”的混合方案。

不使用完整 JSON snapshot。完整 snapshot 会把字段顺序、无关展示字段和置信度小数变化错误地当成算法回归。

不只检查少数字段。弱断言无法阻止日志、模板、粘贴内容和错误类别继续进入结果。

Golden evaluator 应先把 FactorResult 投影成稳定的 semantic answer，再与 Golden answer 比较。

## 4. 目录结构

```text
benchmarks/
  golden/
    README.md
    schema.json
    task-completion/
      verified-completion.json
      claimed-without-verification.json
      final-blocker.json
    user-input-sentiment/
      explicit-correction.json
      negated-failure.json
      neutral-request.json
    repeated-request/
      semantic-reask.json
      repeated-layout-requirement.json
      pasted-server-log.json
    tool-failure-frequency/
      paired-command-failure.json
      successful-command.json
      recovered-command-failure.json
    session-resource-usage/
      verified-resources.json
      mentioned-skill-only.json
      wrapper-and-template-noise.json
    key-sentence-trends/
      action-sequence-constraint.json
      runtime-noun-not-action.json
      pasted-prompt-not-user-habit.json
    semantic-phrase-clusters/
      run-project-variants.json
      separate-report-object.json
      evidence-and-counts.json
scripts/
  evaluate_golden_benchmarks.py
tests/
  test_golden_benchmarks.py
```

## 5. Golden Case Contract

每个 Case 使用同一结构：

```json
{
  "schema_version": "evozeus.factor-golden-case.v1",
  "case_id": "repeated-request.semantic-reask",
  "factor_id": "official.repeated-request",
  "source": {
    "kind": "sanitized-real-session",
    "reason": "真实历史中同一未解决意图被改写后再次提出"
  },
  "input": {
    "session_id": "golden-repeated-semantic-reask",
    "events": []
  },
  "expected": {
    "status": "matched",
    "tags": [],
    "statistics": {},
    "records": [],
    "evidence_event_ids": []
  },
  "forbidden": {
    "tags": [],
    "records": [],
    "evidence_event_ids": []
  },
  "tolerances": {},
  "rationale": "人工确认该请求发生在 assistant 回答之后，且意图仍未解决。"
}
```

字段规则：

- `expected.status`、类别、verdict、tool name、cluster id 等离散字段必须精确匹配。
- `expected.records` 使用 Factor 对应的稳定业务键匹配，例如 `chain_id`、`tool_name`、`resource_key`、`cluster_id`。
- `forbidden` 声明绝不能出现的结果，例如 `unknown_tool`、日志短句、模板 Skill 名、错误语义簇。
- `tolerances` 只用于 similarity、confidence 等浮点值，必须逐字段声明，禁止全局模糊比较。
- `rationale` 解释标准答案为什么成立，便于以后人工审查 Golden 是否需要修订。

## 6. 各 Factor 的标准答案范围

### 6.1 `official.task-completion`

目标：判断任务结果状态，而不是简单判断 Codex turn 是否结束。

首批答案：

| Case | 预期答案 |
| --- | --- |
| 修改完成且测试命令 exit code 为 0 | `verified_completed`，证据包含验证事件 |
| assistant 只说“已完成”，没有验证 | `claimed_completed`，不能升级为 verified |
| 最后明确缺少权限、无法继续 | `blocked`，证据指向最终 blocker |
| 中间失败，随后验证成功 | 最终 `verified_completed`，失败标记为 recovered context |

`task_complete` runtime event 只能证明 turn closure，不能单独证明 `verified_completed`。

### 6.2 `official.user-input-sentiment`

目标：识别用户明确反馈、纠错和问题报告，不把所有普通请求当成高价值反馈。

首批答案：

| Case | 预期答案 |
| --- | --- |
| “不对，改动太大了” | `correction_request` |
| “实际上构建没有失败，已经成功跑完” | `correction_request`，禁止 `problem_report` |
| “运行一下这个项目” | `neutral_request`，Factor status 不应作为 direct gate 命中 |
| “页面打不开并且报错” | `problem_report` |

### 6.3 `official.repeated-request`

目标：识别 assistant 回答后仍未解决、用户再次提出的稳定意图。

首批答案：

| Case | 预期答案 |
| --- | --- |
| “review 这些 factor”后改写为“再检查 factor 算法” | 一条 semantic repeat chain |
| node 排布要求连续重申 5 个 user turns | 4 条 chain、5 个唯一 turns |
| 两次粘贴服务器 nginx 日志 | `not_matched` |
| mirrored user event 重复 | `not_matched` |
| assistant 已明确解决后再次提出新任务 | 不与解决前请求组成 chain |

重复判断必须要求：有效 direct-user 短句、assistant response 间隔、稳定意图相似、未出现解决证据。

### 6.4 `official.tool-failure-frequency`

目标：准确识别失败工具和失败状态，并区分是否已恢复。

首批答案：

| Case | 预期答案 |
| --- | --- |
| `function_call(name=exec_command, call_id=c1)` 对应 output exit code 1 | `exec_command: 1 failure` |
| output exit code 0 | 不计失败 |
| c1 失败、c2 对同一目标成功 | c1 标记 `recovered`，不能作为最终失败 direct gate |
| wrapper output 没有 name，但有 call_id | 必须通过 call_id 解析，禁止 `unknown_tool` |

首批 corpus 的 `unknown_tool` 比例必须为 0。

### 6.5 `official.session-resource-usage`

目标：统计真实使用的 tool、verified skill、MCP、plugin 和 connector。

首批答案：

| Case | 预期答案 |
| --- | --- |
| 真实 tool call 与 MCP tool call | 记录 tool 和 MCP server |
| assistant 只说“可以用某 Skill”但未调用 | 不计 verified skill usage |
| `$HOME`、`$SkillName`、`skill-name-here` | 进入 diagnostics，不进入 resource usage |
| wrapper tool name | 不作为真实工具名 |

计数应同时保留 invocation count、session count 和 evidence refs，报告不得用 unique record count 冒充调用次数。

### 6.6 `official.key-sentence-trends`

目标：在单个 session 或时间轴上提取用户本人表达的动作、顺序和约束。

首批答案：

| Case | 预期答案 |
| --- | --- |
| “先检查迁移，不要删除数据库，最后输出建议” | sequence、negative constraint、output request |
| “运行时配置放在根目录” | 禁止把“运行时配置”识别为运行请求 |
| 用户粘贴大段 Prompt/业务文档 | 文档内部句子不能成为用户习惯关键句 |
| direct-user 明确说“跑起来我看下” | action request |

该 Factor 只用于关键句趋势和 session 详情，不承担跨 session 高频习惯聚类。

### 6.7 `official.semantic-phrase-clusters`

目标：把用户本人表达的同义短句聚成稳定意图簇，并保留变体、计数和证据。

首批答案：

| 输入变体 | 预期答案 |
| --- | --- |
| “把项目拉起来”“tauri 跑起来”“启动 dev server”“跑一下这个项目” | 同一 `intent.run_project` cluster |
| “把报告拉起来看下” | 不能进入 `intent.run_project` |
| 一个 user turn 内重复同一短句 | turn count 只计一次 |
| 多 session 出现同一意图 | 正确输出 turn/session/variant count |

建议稳定输出：

```json
{
  "cluster_id": "intent.run_project",
  "label": "启动/运行项目",
  "representative_phrase": "把项目跑起来",
  "variants": ["把项目拉起来", "tauri 跑起来", "启动 dev server"],
  "intent_type": "run_verify",
  "verb": "启动/运行",
  "object_type": "app_or_project",
  "turn_count": 4,
  "session_count": 3,
  "variant_count": 4,
  "evidence_event_ids": []
}
```

## 7. Evaluator 行为

`evaluate_golden_benchmarks.py` 应：

1. 自动发现 `benchmarks/golden/*/*.json`。
2. 根据 `factor_id` 加载对应 official Factor。
3. 对实际 FactorResult 做稳定 semantic projection。
4. 检查 expected、forbidden 和 tolerance。
5. 输出每个 Case 的字段级 diff。
6. 汇总 Factor 级和全局指标。
7. 发生任何失败时返回非零退出码。

指标至少包括：

- `case_pass_rate`
- `expected_record_precision`
- `expected_record_recall`
- `forbidden_record_count`
- `evidence_ref_accuracy`
- `unknown_tool_share`，仅 tool failure
- `cluster_assignment_accuracy`，仅 semantic phrase cluster

首批合并门槛：所有 Golden Cases 必须通过。后续 Golden corpus 扩大后，可为探索性算法单独输出离线指标，但 official 分支仍要求 100% Golden case pass。

## 8. Golden 治理规则

1. Golden Case 必须由人确认，不允许测试脚本录制当前输出成为答案。
2. Factor 算法 PR 不应同时批量更新 Golden 答案。
3. 如果 Golden 本身错误，必须单独说明：原答案、修订答案、真实证据、修订原因和影响范围。
4. 新发现的线上误判必须先添加失败 Golden Case，再修改 Factor 算法。
5. Golden input 只保留完成判断所需的最小上下文。
6. 不保存真实账号、客户名、secret、绝对路径或完整私有 session。
7. `source.reason` 说明案例来源类型，但不保存可反查个人隐私的 locator。

## 9. 删除与迁移边界

删除：

- `factors/mbti-personality-profile/`
- `factors/usage-sentence-cloud/`
- 两个 Factor 对应的 contract/test/README/SKILL/runtime report 枚举引用

新增：

- `factors/semantic-phrase-clusters/`
- Golden corpus、schema、evaluator 和 tests

保留：

- 报告展示使用画像的能力，但 MBTI 结论改由 SKILL synthesis 输入，不再读取 official MBTI Factor。
- `key-sentence-trends` 继续提供 session-level 关键句，不与 semantic cluster 重复职责。

## 10. 验收

最终交付必须提供：

1. Golden Case 清单及每条人工答案。
2. evaluator 的完整运行结果。
3. 删除后的 official Factor 清单。
4. 新增 semantic phrase cluster Factor 的 contract 和测试。
5. Factor 算法相对 Golden 的逐项 PASS/FAIL 报告。
6. session-signal-skill 与 infra 相关测试通过。

