# Session Golden Benchmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立约 10 个 session-first Golden Benchmarks，新增语义短句聚类 Factor，删除 MBTI 与旧句云 Factor，并让保留 Factor 的输出达到人工标准答案。

**Architecture:** 每个 Golden JSON 同时包含一个脱敏 SessionEnvelope 和 7 个 Factor 的人工答案。Evaluator 动态加载 official factors，将 FactorResult 投影为稳定答案后逐项比较；算法迭代只修改 Factor，不自动更新 Golden。

**Tech Stack:** Python 3.11、`unittest`/`pytest`、现有 `OfficialFactor` contract、JSON fixtures。

---

### Task 1: 收敛 official Factor 集合

**Files:**
- Modify: `tests/test_official_factor_contract.py`
- Modify: `tests/test_official_factors.py`
- Delete: `factors/mbti-personality-profile/`
- Delete: `factors/usage-sentence-cloud/`
- Create: `factors/semantic-phrase-clusters/FACTOR.xml`
- Create: `factors/semantic-phrase-clusters/spec.json`
- Create: `factors/semantic-phrase-clusters/session.json`
- Create: `factors/semantic-phrase-clusters/factor.py`

- [ ] 修改 expected factor set 为 7 个保留 Factor，先运行 contract test，确认因旧目录仍存在且新目录缺失而失败。
- [ ] 删除两个旧 Factor 目录，建立 semantic factor 的最小 contract 与空实现。
- [ ] 运行 `python3 -m pytest -q tests/test_official_factor_contract.py`，确认 Factor 集合与 contract 通过。

### Task 2: 建立 Session-first Golden runner

**Files:**
- Create: `benchmarks/golden/README.md`
- Create: `src/evozeus_session_signal_skill/golden.py`
- Create: `scripts/evaluate_golden_sessions.py`
- Create: `tests/test_golden_sessions.py`

- [ ] 先写失败测试，要求 loader 自动发现 `benchmarks/golden/sessions/*.json`，并校验每个 session 都包含 7 个 Factor 答案。
- [ ] 实现 factor registry、Golden loader 和稳定 answer projector。
- [ ] 实现 recursive diff：字典精确比较，列表按 canonical JSON 排序，输出 session/factor/field。
- [ ] 运行单测，确认缺少 Golden sessions 时测试按预期失败。

### Task 3: 添加约 10 个人工 Golden Sessions

**Files:**
- Create: `benchmarks/golden/sessions/01-verified-completion.json`
- Create: `benchmarks/golden/sessions/02-final-blocker.json`
- Create: `benchmarks/golden/sessions/03-explicit-correction.json`
- Create: `benchmarks/golden/sessions/04-semantic-repeated-request.json`
- Create: `benchmarks/golden/sessions/05-pasted-log-not-request.json`
- Create: `benchmarks/golden/sessions/06-tool-failure-and-recovery.json`
- Create: `benchmarks/golden/sessions/07-resource-usage.json`
- Create: `benchmarks/golden/sessions/08-key-sentence-constraints.json`
- Create: `benchmarks/golden/sessions/09-run-project-phrases.json`
- Create: `benchmarks/golden/sessions/10-pasted-prompt-noise.json`

- [ ] 从已审查的真实问题类型整理最小脱敏 events，不复制完整原始 session。
- [ ] 为每个 session 人工填写全部 7 个 Factor 答案，包括明确的 `not_matched`。
- [ ] 运行 `python3 scripts/evaluate_golden_sessions.py`，记录当前 Factor 与 Golden 的失败清单。

### Task 4: 按 Golden 修复 Factor 算法

**Files:**
- Modify: `factors/task-completion/factor.py`
- Modify: `factors/user-input-sentiment/factor.py`
- Modify: `factors/repeated-request/factor.py`
- Modify: `factors/tool-failure-frequency/factor.py`
- Modify: `factors/session-resource-usage/factor.py`
- Modify: `factors/key-sentence-trends/factor.py`
- Modify: `factors/semantic-phrase-clusters/factor.py`
- Modify: `src/evozeus_session_signal_skill/nlp.py`
- Modify: `tests/test_official_factors.py`

- [ ] Task completion：区分 runtime closure、claimed completion 和 verified completion，最终 blocker 优先。
- [ ] Sentiment：优先处理“实际上没有失败”等纠错/否定表达，纯 neutral request 不作为 direct gate 命中。
- [ ] Repeated request：要求 assistant response 间隔，排除 shell/log/config 粘贴，保留语义改写重复。
- [ ] Tool failure：按 `call_id` 关联 call/output，解析真实 tool name，标记 recovered/unrecovered。
- [ ] Resource usage：只把结构化字段或明确 assistant 使用声明作为 verified resource，模板名进入 diagnostics。
- [ ] Key sentence：排除粘贴 Prompt，修复“运行时配置”被当成 action request。
- [ ] Semantic phrase：实现短句切分、动作/对象归一化、稳定 cluster id、变体和 evidence 计数。
- [ ] 每修一个 Factor 都运行对应单测和 Golden evaluator，直到 10 个 session 全部通过。

### Task 5: 清理 Skill、文档和 Infra 引用

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `docs/architecture/factor-system-concepts.md`
- Modify: `../evozeus-infra/src/evozeus_runtime/reports/ledger_browser.py`
- Modify: `../evozeus-infra/src/evozeus_runtime/reports/ai_usage_profile.py`
- Modify: `../evozeus-infra/src/evozeus_runtime/use_cases/generate_ai_usage_profile_report.py`
- Modify: `../evozeus-infra/tests/unit/test_official_factor_bridge.py`
- Modify: `../evozeus-infra/tests/integration/test_ai_usage_profile_report.py`
- Modify: `../evozeus-infra/tests/unit/test_ai_usage_profile_renderer.py`

- [ ] 删除 official MBTI/usage cloud 枚举和说明；说明 MBTI 由 Skill synthesis 负责。
- [ ] 报告改为消费 `semantic_phrase_cluster_set`，不再读取 `high_frequency_phrase_set`。
- [ ] 修复 high-quality synthesis：neutral sentiment 和普通 completed session 不能单独升级为高质量。
- [ ] 更新 official bridge、ledger browser 和 report tests 的 Factor 集合。

### Task 6: 全量验证

**Files:**
- Verify only

- [ ] 运行 `python3 scripts/evaluate_golden_sessions.py`，预期 10 个 Session × 7 个 Factor 全部 PASS。
- [ ] 在 session-signal repo 运行 `python3 -m pytest -q`。
- [ ] 在 infra repo 运行 `python3 -m pytest -q`。
- [ ] 运行一次本地 official visualization 链路，确认只桥接 7 个 Factor，报告中不再出现 MBTI Factor 与旧句云 Factor。
- [ ] 检查 git diff，只包含 Golden、Factor、文档和对应 infra 消费修改。

