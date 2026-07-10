# EvoZeus Session Golden Benchmarks 设计

- Status: 已确认
- Date: 2026-07-11
- Owner: EvoZeus factor maintainers

## 1. 一句话设计

挑选一批有代表性的真实 session，脱敏并缩短后保存；人工仔细 review 每个 session，为这个 session 写出所有 Factor 的标准答案。

以后调整 Factor 算法时，对同一批 session 重新运行全部 Factor，并把实际结果与人工答案逐项比较。

Golden Benchmark 是答案，不根据当前算法自动生成，也不能为了让测试通过而随意修改。

## 2. 目录

```text
benchmarks/golden/
  README.md
  sessions/
    01-verified-completion.json
    02-final-blocker.json
    03-explicit-correction.json
    04-semantic-repeated-request.json
    05-pasted-log-not-request.json
    06-tool-failure-and-recovery.json
    07-resource-usage.json
    08-key-sentence-constraints.json
    09-run-project-phrases.json
    10-pasted-prompt-noise.json
scripts/
  evaluate_golden_sessions.py
tests/
  test_golden_sessions.py
```

## 3. 一个 Golden Session 的结构

```json
{
  "schema_version": "evozeus.session-golden.v1",
  "golden_id": "04-semantic-repeated-request",
  "source_note": "从真实历史中的重复请求场景脱敏整理",
  "review_note": "用户在 assistant 回答后重新提出同一个未解决意图",
  "session": {
    "session_id": "golden-04",
    "events": []
  },
  "expected_factor_results": {
    "official.task-completion": {},
    "official.user-input-sentiment": {},
    "official.repeated-request": {},
    "official.tool-failure-frequency": {},
    "official.session-resource-usage": {},
    "official.key-sentence-trends": {},
    "official.semantic-phrase-clusters": {}
  }
}
```

每个 Factor 都必须有答案。没有命中时也明确写：

```json
{
  "status": "not_matched",
  "records": [],
  "evidence_event_ids": []
}
```

答案只保存影响算法判断的稳定字段：

- `status`
- 主要 `tags` 或 verdict
- 关键 `statistics`
- dataset 中的核心 records
- `evidence_event_ids`

不比较 presentation、字段顺序、无关 confidence 小数或页面展示内容。

## 4. 首批代表性 Session

| Session | 主要用于检查 |
| --- | --- |
| 已修改代码且测试通过 | task completion、tool success、resource usage |
| 最终缺少权限无法继续 | blocked、用户情绪、无重复请求 |
| 用户说“不对，改动太大” | correction request、关键约束 |
| 用户改写后再次提出同一请求 | repeated request、semantic phrase cluster |
| 两次粘贴 nginx/server 日志 | 日志不能算重复请求、关键句或用户习惯 |
| 命令先失败后成功 | tool name、failure、recovery、最终完成状态 |
| 明确调用 Skill、MCP 和工具 | verified resource usage、模板噪声排除 |
| “先检查，不要删除，最后输出建议” | sequence、negative constraint、output request |
| “项目拉起来、tauri 跑起来、启动 dev server” | 同一运行项目语义簇 |
| 用户粘贴长 Prompt 或业务文档 | 文档内容不能污染关键句和使用习惯 |

实际落地时可以继续增加 Session，但首批控制在 10 个左右，保证每一个答案都经过人工 review。

## 5. Factor 调整

保留并进入 Golden 对比：

1. `official.task-completion`
2. `official.user-input-sentiment`
3. `official.repeated-request`
4. `official.tool-failure-frequency`
5. `official.session-resource-usage`
6. `official.key-sentence-trends`
7. `official.semantic-phrase-clusters`

删除：

1. `official.mbti-personality-profile`
2. `official.usage-sentence-cloud`

MBTI 后续属于 SKILL 综合分析，不再作为单一 Factor。

`semantic-phrase-clusters` 替代句云，输出语义意图、代表句、表达变体、turn 数、session 数和 evidence refs。

## 6. Evaluator

`evaluate_golden_sessions.py` 只做四件事：

1. 加载一个 Golden Session。
2. 对它运行全部 7 个 official Factors。
3. 抽取稳定字段，与 `expected_factor_results` 比较。
4. 输出哪个 session、哪个 Factor、哪个字段不一致，并返回非零退出码。

示例输出：

```text
PASS 01-verified-completion official.task-completion
PASS 01-verified-completion official.session-resource-usage
FAIL 05-pasted-log-not-request official.repeated-request
  expected.status: not_matched
  actual.status: matched
```

## 7. Golden 维护规则

1. Golden 答案由人工 review 后填写。
2. 修改 Factor 算法时，默认只能修改算法，不能修改答案。
3. 发现新的误判时，先增加一个 Golden Session，再修算法。
4. 如果确认答案本身写错，必须单独说明修改原因。
5. Session 必须脱敏，不保存账号、客户名、secret、绝对路径或完整私有聊天。

## 8. 验收标准

1. 约 10 个脱敏代表性 Golden Sessions。
2. 每个 Session 都有 7 个 Factor 的人工标准答案。
3. evaluator 能逐 Session、逐 Factor 输出 PASS/FAIL 和字段差异。
4. 删除 MBTI 和 usage sentence cloud Factor 及其引用。
5. 新增 semantic phrase clusters Factor。
6. 全部 Golden Sessions 通过后，Factor 算法才算达到当前基准。

