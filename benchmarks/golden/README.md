# Session Golden Benchmarks

这里有两套数据，职责不同，不能混称：

## `real-sessions/`：真实 Golden Benchmark

- 该目录包含脱敏后仍可能保留业务语境的真实协作记录，只保存在授权的本地评测环境，不进入公开 Git 仓库。
- CI 缺少本地真实数据集时跳过真实样本断言；公开回归由 `sessions/` micro cases 覆盖。
- 直接从本机 Codex rollout JSONL 的主线程抽样。
- 必须由首条 `session_meta.payload.thread_source = "user"` 证明是主线程。
- 真实用户消息必须有 `codex_user_origin = event_msg | event_msg_mirror | response_item_mirror`。
- 保留真实用户、AI、工具、任务结束事件的原始顺序和原始 JSONL 行号。
- 删除 reasoning、系统上下文和自动注入内容；对路径、私有飞书链接和 secret 脱敏。
- 每个 Session 都包含人工逐条审阅后的 7 个 official Factor 标准答案：`task-completion`、`user-input-sentiment`、`repeated-request`、`tool-failure-frequency`、`session-resource-usage`、`key-sentence-trends`、`semantic-phrase-clusters`。
- 页面和真实算法迭代默认使用这套数据。

`provenance` 保存来源种类、Session ID 哈希、source fingerprint、日期、原始/保留事件数、真实用户轮次和脱敏/截断计数，用于证明样本确实来自 Codex 历史。

## `sessions/`：Micro Cases

这里的 10 个短 Session 是手工构造的最小测试夹具，不是真实 Codex 历史。它们只用于快速定位单个算法边界，例如：

- 用户明确否定结果；
- 粘贴日志不能算重复请求；
- 工具失败后恢复；
- Prompt 正文不能污染用户习惯。

## 维护原则

Golden 是算法迭代的人工答案：默认修改 Factor 实现，不为了让测试通过而反向修改 Golden。发现新误判时，先从真实 Session 增加脱敏样本和人工答案，再修改算法。

评分命令：

```bash
python3 scripts/evaluate_golden_sessions.py --dataset micro
python3 scripts/evaluate_golden_sessions.py --dataset real --threshold 0.9
```

生成链路：

```bash
python3 scripts/sample_real_codex_golden_sessions.py <rollout.jsonl>...
python3 scripts/finalize_real_golden_sessions.py
python3 scripts/render_golden_session_report.py
```
