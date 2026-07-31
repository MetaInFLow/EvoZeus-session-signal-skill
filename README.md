# EvoZeus-session-signal-skill

`EvoZeus-session-signal-skill` 当前定位为：**识别高价值 AI 协作历史记录的 Session Signal SKILL + official factor tools**。

当前正式版本为 `v0.1.0`，由 EvoZeus 产品清单按 exact tag、commit 和 checksum 安装；唯一 UAT 使用同一 Repo 的 `uat/current` 固定 Commit，不单独创建第二套测试版本名称。

这个名字强调主角是 `SKILL.md` 方法层：它负责把聊天记录里的 session signals 合成为可复核的高价值候选；`factors/<slug>/` 是这套 SKILL 可以调用、解释和校准的 signal tools。这里的 `official` 只表示 factor contract / tool 稳定，不表示“所有可安装官方因子包的仓库”。它用于在当前 Codex / agent session 中找出需要被总结、沉淀或复盘的 sessions：大多数正常完成、低信息量、一次性任务应跳过；少数好案例、失败链路、用户纠偏、重复返工、工具卡点和异常资源使用才进入沉淀队列。

顶层 [SKILL.md](SKILL.md) 是这套方法的入口：factor tool 负责分析聊天记录并产出结构化信号，`SKILL.md` 负责说明如何利用这些 tool 结果判断是否值得沉淀、建议沉淀成什么类型、证据是什么、下一步怎么写。

如果需要先理解“为什么会有 Factor、Factor / SKILL / Runner / Ledger / Review Page 分别负责什么”，先读 [EvoZeus Factor 系统概念梳理](docs/architecture/factor-system-concepts.md)。这份文档是当前项目的概念边界说明，避免把 factor signal、最终高价值判断、页面展示和人工复核混在一起。

## 项目文档

- [Session Signal SKILL 系统设计](docs/design/session-signal-skill-system-design.md)
- [Factor 系统概念梳理](docs/architecture/factor-system-concepts.md)
- [Session Signal SKILL 系统实施计划](docs/superpowers/plans/2026-06-24-session-signal-skill-system.md)

## 稳定流程

```text
scanner/runtime
  -> official factors
  -> candidate synthesis
  -> high-quality session review page
  -> human review
  -> SKILL / guardrail / checklist
```

它只放五类东西：

1. 稳定 Python `OfficialFactor` 抽象类。
2. 面向 SKILL 候选识别的 `SKILL.md` 方法说明。
3. 官方 Factor spec schema。
4. 面向值得沉淀的 session 识别的 official factor tools。
5. `FACTOR.xml` contract、算法实现和脱敏测试向量。

本 repo 不再是 official pack 发布仓库，不保存真实业务 Factor pack、release manifest、checksum、SBOM、attestation 或 lab promotion 状态。`official` 在这里表示“官方稳定的高价值历史记录识别方法和 tools”，不是最终评分模型，也不是人工判断的替代。

## SKILL Candidate Method

当前 session signal factors 共同组成一套本地、轻量、可解释的 SKILL 候选识别方法，但它们不是同级决策信号：

- `user-input-sentiment`：识别用户是否不满、纠错或报告问题，用来发现 guardrail / interaction SKILL 候选。
- `task-completion`：判断任务是否完成、阻塞、未知或未完成，用来区分好案例 workflow 与失败复盘。
- `repeated-request`：发现用户是否反复追问同一未解决请求，用来沉淀澄清问题和验收 checklist。
- `tool-failure-frequency`：定位工具失败是否影响任务；默认是 diagnostic，只有和未完成、阻塞或明确环境规则叠加时才支撑 troubleshooting。
- `session-resource-usage`：观察 tool、skill、MCP server 等资源是否被正确使用；默认是 diagnostic，用来还原可复用步骤。
- `key-sentence-trends`：抽取用户和 assistant 的关键行动、对象、否定和交付句；默认是 diagnostic，用来写 SKILL 的触发条件和步骤。
- `semantic-phrase-clusters`：把用户本人的同义短句归并为稳定意图簇；默认是 diagnostic，用于理解跨表达方式的请求习惯。

MBTI 是 Session Signal SKILL 基于多个 official factor signals 生成的综合画像，不是 official Factor，不进入 official Factor 数量，也不能单独驱动 high-quality 判断。

当前建议生命周期：

| 生命周期 | Factor |
| --- | --- |
| `active` | `user-input-sentiment`、`task-completion`、`repeated-request` |
| `diagnostic` | `tool-failure-frequency`、`session-resource-usage`、`key-sentence-trends`、`semantic-phrase-clusters` |

这些 factor 输出的是可筛选信号，不是单一总分。标准用法不是处理全部 session，而是先把 session 分成：`success_skill_candidate`、`problem_skill_candidate`、`failure_skill_candidate`、`repeat_skill_candidate`、`workflow_skill_candidate`、`review_needed` 和 `not_skill_candidate`。好案例和问题案例都可能是高价值 SKILL 候选。

最终 HTML 报告应有独立 `High-Quality Session Review Page`：基于 active gate 和 diagnostic factor 的结果筛出 `high_quality_session`，把分析范围内其余 session 标成 `low_quality_session`，并展示每个高质量判断背后的 `factor_result_reasons`、证据引用和人工复核状态。报告必须明确 scanned / analyzed / not analyzed 的口径，不能把已扫描但未跑 factor 的 session 当成低质量。该页面只做展示期合成，不向 ledger 写入重复数据。

## 边界

| 属于本 repo | 不属于本 repo |
| --- | --- |
| `src/evozeus_session_signal_skill/factor.py` | 真实业务 Factor pack |
| `SKILL.md` | 最终评分模型 |
| `schemas/official-factor-spec.schema.json` | pack release manifest |
| `factors/<factor-slug>/FACTOR.xml` | checksum / SBOM / attestation |
| `factors/<factor-slug>/factor.py` | runtime install source |
| `tests/` | 真实 session 原文 |

## Official Contract

官方 Factor spec 比 lab 草案多三层约束：

- `stability` 必须是 `official`。
- `compatibility.evozeus_protocol` 必须声明协议范围。
- `governance.owner` 必须声明维护责任。
- `title_i18n` 必须声明 `zh-CN` / `en-US` 双语标题。
- `summary_i18n` 必须声明 `zh-CN` / `en-US` 双语功能说明。

Official Factor 仍然只是 official factor，不代表默认安装的业务 Factor。它的首要职责是把“如何识别值得沉淀成 SKILL 的 session 信号”沉淀成稳定 contract、算法实现和可验证样本。

## Official Factor Layout

官方 Factor全部平铺在 `factors/` 下。每个 factor 单元自带代码、spec 和脱敏输入：

```text
factors/
  repeated-request/
    FACTOR.xml
    factor.py
    spec.json
    session.json
  semantic-phrase-clusters/
    FACTOR.xml
    factor.py
    spec.json
    session.json
  tool-failure-frequency/
    FACTOR.xml
    factor.py
    spec.json
    session.json
  key-sentence-trends/
    FACTOR.xml
    factor.py
    spec.json
    session.json
  task-completion/
    FACTOR.xml
    factor.py
    spec.json
    session.json
  user-input-sentiment/
    FACTOR.xml
    factor.py
    spec.json
    session.json
  session-resource-usage/
    FACTOR.xml
    factor.py
    spec.json
    session.json
```

当前 official factors 覆盖：

| Factor | 输入类型 | 输出结果 | 可视化输出 | SKILL 候选识别贡献 |
| --- | --- | --- | --- | --- |
| `repeated-request` | `session` | `evidence_record_set` | `builtin.table.v1` | 重复追问越多，越可能说明前一次回答没有解决问题；适合沉淀澄清问题和验收 checklist。 |
| `tool-failure-frequency` | `session` / `project` / `scan_record_set` | `frequency_distribution` | `builtin.bar_chart.v1` | Diagnostic。工具失败是过程摩擦信号；和未完成或用户不满叠加时才适合沉淀 troubleshooting。 |
| `key-sentence-trends` | `session` / `project` / `scan_record_set` | `key_sentence_trend` | `builtin.line_chart.v1` / `builtin.heatmap.v1` | Diagnostic。通过关键行动、对象、否定和交付句解释过程，辅助写 SKILL 触发条件和步骤。 |
| `task-completion` | `session` | `task_completion_verdict` | `builtin.table.v1` | 直接判断任务闭环状态；普通完成且无异常通常跳过，阻塞和未完成进入 failure SKILL 候选。 |
| `user-input-sentiment` | `session` / `project` / `scan_record_set` | `user_sentiment` / `frequency_distribution` | `builtin.bar_chart.v1` / `builtin.table.v1` | 识别满意、不满、纠错和问题反馈；用户纠偏和问题反馈是强 guardrail 候选信号。 |
| `session-resource-usage` | `session` / `project` / `scan_record_set` | `session_resource_usage` / `frequency_distribution` | `builtin.bar_chart.v1` / `builtin.table.v1` | Diagnostic。验证 tool、skill、MCP server 等资源是否真实支撑任务；用于还原可复用步骤和依赖。 |
| `semantic-phrase-clusters` | `session` | `semantic_phrase_cluster_set` | `builtin.table.v1` / `builtin.json.v1` | Diagnostic。归并 direct-user 同义短句，保留代表短句、变体、计数和事件证据，用于理解稳定请求习惯。 |

## Factor Input / Result / Visualization Contract

Official Factor 输入由 runtime materialize 为统一 envelope。输入可以是单个 session、project、scan record set、ledger query、历史 factor result set 或 mixed context。

Official Factor 输出统一为 `OfficialFactorResult`。结果包含：

- `target_type` / `target_id`：本次分析目标。
- `scores` / `statistics`：小型数值和聚合结果。
- `datasets`：可落账 read model，例如 semantic phrase cluster set。
- `presentations`：可插拔前端组件的展示 contract，例如 `builtin.table.v1`。
- `evidence_refs`：指向 session event、scan record 或 prior factor result 的证据引用。

FactorResult 不携带前端代码。前端组件由 infra 的 visualization component registry 加载；组件不可用时必须 fallback 到 `builtin.table.v1` 或 `builtin.json.v1`。

新增 factor 的完整步骤见 [新建 Official Factor 指南](docs/guides/create-official-factor.md)。

## Runtime Integration

当前 P0 发布形态是 source checkout integration：`evozeus-runtime` 通过 `--official-repo-root /path/to/EvoZeus-session-signal-skill` 读取 `factors/` 和 `templates/`。

普通 Chat 的只读 Lesson 候选判断使用固定 API `evozeus.session-signal.lesson-candidate.v1`：

```bash
printf '%s' '<request-json>' | PYTHONDONTWRITEBYTECODE=1 python3 scripts/evaluate_lesson_candidate.py
```

该 CLI 拥有 correction / durable-rule 判断、注册目标选择与 model-only guidance 合同。它只读 stdin 并写 stdout，不持久化 prompt 或候选；`contracts/lesson-candidate-v1.json` 固定未来渠道 attachment。当前 Release / package version 仍为 `v0.1.0`，合同中的 `v0.1.1` 属于 Unreleased，等待后续产品渠道发布。产品渠道发现、组件摘要校验和 Hook fail-open 由调用方负责。完整合同见 [普通 Chat Lesson Candidate 只读合同](docs/design/normal-chat-lesson-candidate-contract.md)。

这意味着使用者需要同时具备：

- `EvoZeus-infra`：提供 `evozeus-runtime` CLI、scanner、runner、ledger 和 HTML 报告生成。
- `EvoZeus-session-signal-skill`：提供七个 official factors、MBTI 综合画像方法、Session Signal SKILL 方法说明和报告模板资源。

安装依赖：

```bash
python3 -m pip install -e ".[nlp]"
```

缺少 `scikit-learn`、`jieba`、`rapidfuzz` 或 `snownlp` 时，相关 factor 会失败或输出降级结果。

如果只 `pip install EvoZeus-session-signal-skill`，不能假设 `factors/` 和 `templates/` 已经可被 runtime 发现。面向用户的稳定运行方式是把本 repo 作为 source checkout 传给 `evozeus-runtime`：

```bash
evozeus-runtime session-insights \
  --workspace "$HOME" \
  --official-repo-root "/path/to/EvoZeus-session-signal-skill"
```

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
