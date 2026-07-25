# AI 使用画像与 Session 价值报告模板

用途：把 session scanner 和 official factors 的结果渲染成普通用户能读懂的 AI 使用画像与 session 价值复核报告。

边界：

- 本目录只放模板和数据契约。
- 不存放某次真实扫描的报告产物。
- 模板只消费固定 `reportData` JSON，不直接读取 raw session。
- 实际报告应输出到 EvoZeus cluster 的运行产物区，例如 `30-ops/session-reports/<date>-<report-name>/`。

当前页面覆盖的结果类型：

- MBTI/session-derived 使用画像
- 高质量 session 候选与低质量 / 待复核 session 列表
- 扫描总览：已扫描 session、已跑 factor session、factor 结果数
- 高频使用句
- 关键句趋势
- 用户反馈分布
- 重复请求
- 任务完成状态
- 工具失败
- 资源使用
- 优势、摩擦点和优化建议
- MBTI evidence marker 明细
