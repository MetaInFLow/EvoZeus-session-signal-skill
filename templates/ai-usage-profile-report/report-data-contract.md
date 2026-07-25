# AI 使用画像与 Session 价值报告数据契约

状态：对内设计稿配套说明
用途：把 HTML 模板需要的内容固定成可稳定生成的字段
原则：页面只消费 `reportData`，不直接读取 raw session

## 核心判断

这份报告不能靠 LLM 每次自由发挥。正确路径是两段式：

1. 确定性提取：scanner 和 official factors 产出结构化结果。
2. 受控生成：规则库把结构化结果映射成用户能看懂的标题、解释和建议。

也就是说，LLM 可以润色单句，但不能决定页面结构、字段含义、证据来源和建议触发条件。

参与确定性提取的 official Factor 固定为七个：`task-completion`、`user-input-sentiment`、`repeated-request`、`tool-failure-frequency`、`session-resource-usage`、`key-sentence-trends`、`semantic-phrase-clusters`。MBTI 由 Session Signal SKILL 综合这些结构化信号生成，不是 official Factor。

## 固定字段

| 页面字段 | 稳定来源 | 生成方式 | 兜底规则 |
|---|---|---|---|
| `meta.subject` | 扫描任务配置 | 用户名、账号名或匿名用户 | 无用户名时显示“用户” |
| `meta.scanLabel` | scanner summary | 最近一次扫描、最近 7 天、指定项目等 | 无窗口时显示“本次扫描” |
| `meta.sessionId` | scanner summary | 代表性 session id 或 batch id | 多个 session 用 batch id |
| `meta.scanScope` | scanner summary | 脱敏样本、个人会话、项目会话等 | 未知时显示“已扫描会话” |
| `meta.generatedAt` | 生成任务时间 | ISO 日期 | 缺失时用当前生成日期 |
| `profile.code` | Session Signal SKILL 综合画像 | `inferred_type` 转用户文案，比如 `INTJ 倾向` | 证据不足时显示“样本不足” |
| `profile.displayName` | 人群画像命名表 | MBTI 倾向 + 最高行为信号映射 | 未命中时显示“协作画像待确认” |
| `profile.confidence` | SKILL 综合画像 statistics | 归一化置信度 | 小于阈值时降级为“低置信度画像” |
| `profile.oneSentence` | 文案模板库 | 类型名 + 主要习惯 + 主要风险 | 证据不足时提示“需要更多会话样本” |
| `metrics` | factor statistics + SKILL 综合画像 + session review stats | MBTI 倾向、画像置信度、证据 marker、高质量候选、待复核/低价值、factor 结果数 | 指标缺失时隐藏该卡片 |
| `sessionReview.stats` | 旧版 high-quality session review / scan summary | 已扫描 session、已跑 factor、候选数、待复核数、factor 结果数 | 无旧报告时隐藏 Session 价值复核区 |
| `sessionReview.officialFactorIds` | official factor runner | 参与复核的 factor id 列表 | 空列表时隐藏 factor chip |
| `sessionReview.sessions` | high-quality session review records | 每条 session 的 id、标题、项目、标签、候选类型、分数、事件数、用户开头和信号原因 | 无记录时显示“暂无可复核 session” |
| `factorSummary` | factor results summary | 把每个 factor 的状态和核心结果压缩成一张总览卡 | 无命中时显示“暂无明显信号” |
| `semanticPhraseClusters` | `official.semantic-phrase-clusters` | 代表短句、语义变体、次数、cluster id 和 event refs | 空数据时隐藏语义短句簇区块 |
| `keySentences` | `official.key-sentence-trends` | 日期、角色、关键句、次数、关系类型 | 空数据时隐藏关键句区块 |
| `signalGroups` | official factor datasets | 情绪、重复请求、任务闭环、工具失败、资源使用等分组展示 | 每组最多展示 4 行 |
| `dimensions` | SKILL 综合画像 dimensions | I/E、N/S、T/F、J/P 的选择、分数和证据数 | 单维证据不足时标记“未确认” |
| `habits` | insight rules | 高分维度 + 关键句趋势映射成使用习惯 | 少于 2 条时补充“样本不足”说明 |
| `traits` | insight rules | 正向信号生成优势，负向信号生成摩擦点 | 每类最多 2 条，避免堆砌 |
| `recommendations` | recommendation rules | 信号组合触发建议和示例 | 无触发时给通用提示词优化建议 |
| `sourcePlan` | 静态模板 | 解释每类内容来自哪里 | 固定展示，不依赖 session |
| `evidence` | SKILL 综合画像 / `profile_dimension_evidence` | event id、轴线、倾向、命中 marker、脱敏短句、权重 | 只展示短句，不展示完整原文 |

## 推荐生成链路

1. `scan_summary` 记录扫描窗口、session 数量、session id、覆盖范围和生成时间。
2. 七个 official factors 统一输出结构化 signals，包括关键句趋势、语义短句簇、重复请求、任务完成、工具失败、资源使用和情绪倾向等。
3. Session Signal SKILL 综合多个 factor signals 生成 MBTI 倾向、维度证据和画像置信度；该结果不计入 official Factor results。
4. `report_composer` 读取 factors、SKILL 综合画像和旧版 session review 结果，生成固定 `reportData` JSON，其中 `factorSummary` 是总览，`sessionReview` 是可筛选复核列表，`semanticPhraseClusters` 和 `keySentences` 是可展开证据。
5. `copy_rules` 把内部字段转成人能看懂的中文，比如把 `Judging` 转成“结构闭环”。
6. `recommendation_rules` 根据触发条件生成建议，比如“上下文过长 + 高 J 倾向”触发“背景分批输入”。
7. HTML 模板只渲染 `reportData`，不做业务判断。

## 需要固定的规则库

| 规则库 | 作用 | 示例 |
|---|---|---|
| `profile_name_map` | 把 MBTI 倾向转成报告标题 | `INTJ` -> `战略型拆解者` |
| `dimension_label_map` | 把维度转成用户语言 | `T` -> `判断标准` |
| `habit_rules` | 把信号组合转成习惯卡片 | `N 高 + J 高` -> `先定义问题，再进入细节` |
| `trait_rules` | 把信号转成优势和摩擦点 | `证据边界强` -> `质量控制能力强` |
| `recommendation_rules` | 把风险转成可执行建议 | `上下文密度高` -> `背景分批输入` |
| `session_review_rules` | 把旧版高质量 session review 转成复核模块 | `quality_score > 0` -> 高质量候选，`score = 0` -> 低质量 / 待复核 |
| `evidence_rules` | 选择可展示证据 | MBTI 综合画像保留全部 marker 明细；其他证据先脱敏再截断 |

## 存储位置

| 内容 | 应放位置 | 原因 |
|---|---|---|
| HTML 模板 | `10-repos/EvoZeus-session-signal-skill/templates/ai-usage-profile-report/` | 属于 skill 开发资产，可复用、可测试、可版本管理。 |
| 数据契约 | `10-repos/EvoZeus-session-signal-skill/templates/ai-usage-profile-report/report-data-contract.md` | 属于模板接口说明。 |
| 某次真实报告 | `30-ops/session-reports/<date>-<report-name>/` | 属于运行产物和复盘材料，不应混入开发 repo。 |
| 临时截图 | `output/playwright/` 或报告目录下的 `preview.png` | 用于人工验收，不参与模板逻辑。 |

## 验收标准

1. 任意一批 session 都能生成同一结构的 `reportData`。
2. 证据不足时页面仍完整，不出现空卡片或技术字段。
3. 用户能理解“我的习惯是什么、哪些 session 值得沉淀、哪里强、哪里会拖慢、下次怎么改”。
4. 报告不把 MBTI 说成正式心理测评，只表达“基于 session 的倾向”。
5. 模板不接触 raw session，只接收脱敏后的短句、复核摘要和统计结果。
