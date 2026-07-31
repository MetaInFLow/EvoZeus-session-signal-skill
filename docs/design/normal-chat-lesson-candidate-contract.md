# 普通 Chat Lesson Candidate 只读合同

状态：对内-已通过，等待 companion PR 与产品渠道集成
关联：`MetaInFLow/EvoZeus-CoEvolve#29`

## 目标

普通 Chat 中的明确纠错和长期规则，应能进入 Lesson 候选判断，无需先调用目标 Skill。Session Signal 负责语义判断、目标选择与 model-only 指引；调用方负责提供已验证的注册目标清单和可信组件运行环境。

## 职责边界

| 责任 | Owner |
| --- | --- |
| 高精度 correction / durable-rule 判断 | Session Signal |
| `cwd` containment 与唯一 alias 目标选择 | Session Signal |
| 自然语言 model-only guidance | Session Signal |
| UserPromptSubmit Hook 注册 | CoEvolve |
| 已注册目标 inventory | CoEvolve |
| 产品渠道组件发现、固定版本与脚本摘要校验 | CoEvolve / EvoZeus 产品渠道 |
| Feedback Issue 写入 | 后续用户明确确认后的 CoEvolve 流程 |

## API

固定标识：`evozeus.session-signal.lesson-candidate.v1`

组件 attachment：`contracts/lesson-candidate-v1.json` 固定未来产品渠道要消费的 component version `v0.1.1`、API、entrypoint 与实现文件摘要。本 PR 不创建 tag 或 Release；渠道发布完成前，调用方应把旧版或缺失组件视为 unavailable 并 fail-open。

入口：

```text
python3 scripts/evaluate_lesson_candidate.py
```

CLI 只从 stdin 读取一个 JSON object，并只向 stdout 写一个 JSON object。

请求：

```json
{
  "schema_version": "evozeus.session-signal.lesson-candidate.v1",
  "prompt": "用户当前一轮原文",
  "cwd": "/absolute/current/workspace",
  "targets": [
    {
      "repo": "OWNER/REPO",
      "canonical_path": "/verified/canonical/repo",
      "aliases": ["repo-name", "skill-name"]
    }
  ]
}
```

中性响应：

```json
{
  "schema_version": "evozeus.session-signal.lesson-candidate.v1",
  "candidate": false
}
```

候选响应：

```json
{
  "schema_version": "evozeus.session-signal.lesson-candidate.v1",
  "candidate": true,
  "target_repo": "OWNER/REPO",
  "model_guidance": "自然语言 model-only guidance"
}
```

无法证明归属时 `target_repo` 为 `null`，guidance 要求模型先询问目标 Skill。

## 判断合同

- 明确否定、漏检、误判、不满意、机制缺陷可形成 correction candidate。
- “以后 / 每次 / 始终 / 所有用户”等持续范围词需要同时出现明确行动约束，才形成 durable-rule candidate。
- 中性任务、开放问题和“是不是 / 是否 / 对不对”等歧义询问保持 `candidate=false`。
- 目标优先使用 `cwd` containment；没有 containment 证据时，只接受唯一注册目标 alias。
- 多目标 alias、alias 冲突或无证据均进入 unassigned。

## 隐私与副作用

- 方法和 CLI 不写文件、不访问网络、不创建 Issue、不生成 signal ID。
- 输出不回显 raw prompt、cwd、canonical path 或内部诊断对象。
- guidance 只指导模型先完成业务纠正，再询问是否记录；记录授权和修复授权分别确认。
- 调用方必须设置短 timeout 和 `PYTHONDONTWRITEBYTECODE=1`，并在异常时 fail-open。

## 验收

- correction、durable rule、neutral、ambiguous 均有确定性测试。
- `cwd` containment、唯一 alias、冲突 alias 和 unassigned 均有测试。
- CLI 真实 subprocess 验证 stdin/stdout 合同和零运行时文件。
- 全量 Session Signal tests、Python compile 与 `git diff --check` 通过。
