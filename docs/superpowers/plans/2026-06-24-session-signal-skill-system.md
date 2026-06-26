# Session Signal SKILL 当前定位实施计划

> **给 agentic worker：** 本计划只执行 `evozeus-session-signal-skill` 当前 repo 内的 Session Signal SKILL / official factor tools / review page 方法改造。不要把 `evozeus-factor-lab` 当作 active repo，不要在本计划里改 `evozeus-web` 或 `evozeus-infra`。

**目标：** 把当前 Session Signal SKILL 的判断逻辑从“页面和临时脚本里混合判断”收敛为可测试的 `factor lifecycle -> candidate synthesis -> review page` 流程。

**架构：** `SKILL.md` 定义方法和输出要求；`factors/<slug>/` 提供单信号 factor；`factor_lifecycle.py` 控制 active / diagnostic / deprecated；`candidate_synthesis.py` 组合 factor results；review generator 生成用户可见页面数据。

**技术栈：** Python 3.12、pytest、`FACTOR.xml`、`spec.json`、静态 HTML / JSON review artifact。

---

## 0. 刚刚检查到的事实

1. 当前 `.gitmodules` 只有 4 个 active submodules：`evozeus`、`evozeus-session-signal-skill`、`evozeus-infra`、`evozeus-web`。
2. `evozeus-factor-lab` 已从 active mega repo submodules 移除；`repo-index.md` 明确说它是 private/internal 历史实验仓。
3. 本地仍残留 `10-repos/evozeus-factor-lab/`，且其 `SKILL.md` 有未提交改动；这是单独清理事项，不进入本计划。
4. `evozeus-community` 已重命名为 `evozeus-web`；当前规划不应再使用 `evozeus-community` 作为 repo 名。
5. 当前 design doc 之前错误地写成“五仓整体设计”。新的规划必须回到本 repo 的实际定位：识别高价值 AI 协作历史记录的 Session Signal SKILL + official factor tools。
6. 当前 README 已把 `tool-failure-frequency` 定位为 diagnostic，但 `SKILL.md` 仍把它列为 direct gate，必须修正。

## 1. 当前 Active Topology

| Repo | 当前状态 | 本计划是否修改 |
| --- | --- | --- |
| `evozeus` | active submodule，主协议 / governance | 不修改；只作为最终沉淀去向 |
| `evozeus-session-signal-skill` | active submodule，本计划主体 | 修改 |
| `evozeus-infra` | active submodule，scanner / runner / ledger / report | 不修改；只定义输入/输出接口要求 |
| `evozeus-web` | active submodule，web 入口 | 不修改 |
| `evozeus-factor-lab` | removed from active submodules，private/internal | 不修改；不作为任务对象 |

## 2. 文件结构

- 修改：`SKILL.md`  
  同步 direct gates / diagnostics / deprecated 口径。

- 修改：`README.md`  
  保持与 `SKILL.md` 一致，说明 factor lifecycle 和 review page 价值。

- 修改：`docs/architecture/factor-system-concepts.md`  
  保持概念层一致：factor 不是最终评分，diagnostic/deprecated 不能单独驱动 high-quality。

- 修改：`docs/design/session-signal-skill-system-design.md`  
  保持为本 repo 的定位设计，不写五仓总设计。

- 新增：`src/evozeus_session_signal_skill/factor_lifecycle.py`  
  定义 `active`、`diagnostic`、`deprecated`、`experimental`、`removed`。

- 新增：`src/evozeus_session_signal_skill/candidate_synthesis.py`  
  从 factor results 生成 `CandidateResult`。

- 修改：`factors/*/FACTOR.xml` 和 `factors/*/spec.json`  
  加入 lifecycle 或等价 quality notes；`usage-sentence-cloud` 标为 deprecated 候选。

- 新增 / 修改：`tests/test_factor_lifecycle.py`、`tests/test_candidate_synthesis.py`、`tests/test_official_factor_contract.py`

- 新增 / 修改：`scripts/generate_high_quality_session_review.py`  
  从 synthesis 输出生成 review data，不在 HTML 中写判断逻辑。

## Task 1：修正当前文档口径

**Repo：** `/Users/anthonyf/Documents/EvoZeus-cluster/10-repos/evozeus-session-signal-skill`

**文件：**
- 修改：`SKILL.md`
- 修改：`README.md`
- 修改：`docs/architecture/factor-system-concepts.md`
- 修改：`docs/design/session-signal-skill-system-design.md`

- [ ] **Step 1：修正 `SKILL.md` 的 direct gates**

把 `SKILL.md` 中的 operating rules 改为：

```markdown
2. Separate active gates, diagnostics, and deprecated factors:
   - Active gates: `official.task-completion`, `official.user-input-sentiment`, `official.repeated-request`.
   - Diagnostics: `official.tool-failure-frequency`, `official.session-resource-usage`, `official.key-sentence-trends`.
   - Deprecated candidates: `official.usage-sentence-cloud`.
```

- [ ] **Step 2：补 pruning rules**

在 `SKILL.md` pruning rules 中保留并强化：

```markdown
- Recovered tool failures are diagnostics unless they reveal a reusable environment rule.
- Deprecated factors must never create or upgrade a high-value conclusion.
- A `high_quality_session` is a review candidate, not an accepted SKILL artifact.
```

- [ ] **Step 3：扫描旧 repo 口径**

运行：

```bash
rg -n "evozeus-community|five repo|五个 repo" README.md SKILL.md docs/architecture/factor-system-concepts.md
rg -n "Direct gates:.*tool-failure" SKILL.md
```

预期：

```text
不应再把 evozeus-factor-lab 写成 active component
不应再把 evozeus-community 写成当前 repo 名
不应再把 tool-failure-frequency 写成 direct gate
```

## Task 2：加入 Factor 生命周期

**文件：**
- 新增：`src/evozeus_session_signal_skill/factor_lifecycle.py`
- 新增：`tests/test_factor_lifecycle.py`
- 修改：`tests/test_official_factor_contract.py`

- [ ] **Step 1：写 lifecycle 测试**

创建 `tests/test_factor_lifecycle.py`：

```python
from evozeus_session_signal_skill.factor_lifecycle import FactorLifecycle, can_drive_candidate


def test_active_factor_can_drive_candidate():
    assert can_drive_candidate(FactorLifecycle.ACTIVE)


def test_diagnostic_factor_cannot_drive_candidate_alone():
    assert not can_drive_candidate(FactorLifecycle.DIAGNOSTIC)


def test_deprecated_factor_cannot_drive_candidate():
    assert not can_drive_candidate(FactorLifecycle.DEPRECATED)
```

- [ ] **Step 2：实现 lifecycle**

创建 `src/evozeus_session_signal_skill/factor_lifecycle.py`：

```python
from __future__ import annotations

from enum import StrEnum


class FactorLifecycle(StrEnum):
    EXPERIMENTAL = "experimental"
    ACTIVE = "active"
    DIAGNOSTIC = "diagnostic"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


def can_drive_candidate(lifecycle: FactorLifecycle) -> bool:
    return lifecycle == FactorLifecycle.ACTIVE
```

- [ ] **Step 3：定义当前 7 个 factor 的生命周期**

在 `FACTOR.xml` / `spec.json` 或 contract quality notes 中同步：

```text
active:
  - task-completion
  - user-input-sentiment
  - repeated-request

diagnostic:
  - tool-failure-frequency
  - session-resource-usage
  - key-sentence-trends

deprecated candidate:
  - usage-sentence-cloud
```

- [ ] **Step 4：验证**

运行：

```bash
python -m pytest tests/test_factor_lifecycle.py -q
python scripts/validate_official_factor_spec.py factors/*/spec.json
```

预期：全部通过。

## Task 3：实现 Candidate Synthesis

**文件：**
- 新增：`src/evozeus_session_signal_skill/candidate_synthesis.py`
- 新增：`tests/test_candidate_synthesis.py`

- [ ] **Step 1：写 synthesis 测试**

创建 `tests/test_candidate_synthesis.py`：

```python
from evozeus_session_signal_skill.candidate_synthesis import synthesize_candidate


def result(factor_id, *, lifecycle="active", scores=None, statistics=None):
    return {
        "factor_id": factor_id,
        "lifecycle": lifecycle,
        "status": "matched",
        "scores": scores or {},
        "statistics": statistics or {},
        "evidence_refs": [{"ref_id": "e1", "kind": "user_turn"}],
    }


def test_repeated_request_drives_repeat_candidate():
    output = synthesize_candidate("s1", [
        result("official.repeated-request", scores={"repeated_request_count": 1}),
        result("official.task-completion", statistics={"verdict": "completed"}),
    ])

    assert output["page_label"] == "high_quality_session"
    assert output["candidate_label"] == "repeat_skill_candidate"


def test_diagnostic_only_session_is_low_quality():
    output = synthesize_candidate("s2", [
        result("official.key-sentence-trends", lifecycle="diagnostic", scores={"key_sentence_count": 100}),
        result("official.session-resource-usage", lifecycle="diagnostic", scores={"resource_count": 20}),
    ])

    assert output["page_label"] == "low_quality_session"
    assert output["candidate_label"] == "not_skill_candidate"
    assert len(output["excluded_factors"]) == 2


def test_deprecated_factor_is_excluded():
    output = synthesize_candidate("s3", [
        result("official.usage-sentence-cloud", lifecycle="deprecated", scores={"phrase_count": 100}),
    ])

    assert output["page_label"] == "low_quality_session"
    assert output["excluded_factors"][0]["factor_id"] == "official.usage-sentence-cloud"
```

- [ ] **Step 2：实现 synthesis**

创建 `src/evozeus_session_signal_skill/candidate_synthesis.py`：

```python
from __future__ import annotations

from typing import Any, Mapping

from evozeus_session_signal_skill.factor_lifecycle import FactorLifecycle, can_drive_candidate


def synthesize_candidate(session_id: str, factor_results: list[Mapping[str, Any]]) -> dict[str, Any]:
    reasons = []
    excluded = []

    for item in factor_results:
        factor_id = str(item.get("factor_id", ""))
        lifecycle = FactorLifecycle(str(item.get("lifecycle", "active")))
        scores = item.get("scores") if isinstance(item.get("scores"), Mapping) else {}
        statistics = item.get("statistics") if isinstance(item.get("statistics"), Mapping) else {}

        if not can_drive_candidate(lifecycle):
            excluded.append({
                "factor_id": factor_id,
                "lifecycle": lifecycle.value,
                "reason": "该 factor 只能诊断或已废弃，不能单独驱动高价值候选。",
            })
            continue

        if factor_id == "official.repeated-request" and float(scores.get("repeated_request_count", 0)) > 0:
            reasons.append({"factor_id": factor_id, "kind": "repeat_skill_candidate"})
        elif factor_id == "official.user-input-sentiment" and int(statistics.get("dissatisfaction_turn_count", 0)) > 0:
            reasons.append({"factor_id": factor_id, "kind": "problem_skill_candidate"})
        elif factor_id == "official.task-completion" and statistics.get("verdict") in {"blocked", "not_completed"}:
            reasons.append({"factor_id": factor_id, "kind": "failure_skill_candidate"})

    if not reasons:
        return {
            "session_id": session_id,
            "page_label": "low_quality_session",
            "candidate_label": "not_skill_candidate",
            "factor_result_reasons": [],
            "excluded_factors": excluded,
        }

    return {
        "session_id": session_id,
        "page_label": "high_quality_session",
        "candidate_label": reasons[0]["kind"],
        "factor_result_reasons": reasons,
        "excluded_factors": excluded,
    }
```

- [ ] **Step 3：验证**

运行：

```bash
python -m pytest tests/test_candidate_synthesis.py -q
```

预期：全部通过。

## Task 4：把 Review Page 数据改为 synthesis 输出

**文件：**
- 新增 / 修改：`scripts/generate_high_quality_session_review.py`
- 新增 / 修改：`tests/test_review_artifact_generator.py`
- 修改：`artifacts/high-quality-session-review/index.html`

- [ ] **Step 1：生成数据必须包含这些字段**

`real-review-data.json` 中每条 analyzed session 必须包含：

```text
session_id
title
source_ref
page_label
candidate_label
factor_result_reasons
excluded_factors
human_quality_review
opening_user_events
assistant_action_events
factor_results
```

- [ ] **Step 2：页面必须展示这些列**

Review page 主表必须展示：

```text
#
已分析聊天记录
是否高价值
判定类型
强度 / 证据数
原因
session_id
```

- [ ] **Step 3：页面必须展示证据详情**

每条 session 的详情区必须展示：

```text
这段聊天在讲什么
用户关键原话
assistant 关键动作
factor_result_reasons
excluded_factors / contradictions
human_quality_review
```

- [ ] **Step 4：验证页面**

运行：

```bash
python -m pytest -q
python scripts/validate_official_factor_spec.py factors/*/spec.json
```

如果有 Playwright smoke 脚本，则补充运行：

```bash
node scripts/check_high_quality_session_review.mjs
```

预期：测试通过，页面能显示全部 analyzed sessions，且 diagnostic/deprecated factor 不单独产生 high-quality。

## Task 5：处理 Repo 拓扑发现

**不执行删除，只更新规划口径。**

- [ ] **Step 1：确认本计划没有把 `evozeus-factor-lab` 当作执行对象**

运行：

```bash
rg -n "[R]epo：.*/evozeus-factor-lab|[修]改：.*evozeus-factor-lab|[新]增：.*evozeus-factor-lab|[c]d .*/evozeus-factor-lab" docs/superpowers/plans/2026-06-24-session-signal-skill-system.md
```

预期：无命中。

- [ ] **Step 2：单独记录本地残留**

不要在本计划里删除 `10-repos/evozeus-factor-lab/`。如需清理，另起一个 cleanup 任务，先检查它自己的 dirty 状态：

```bash
git -C /Users/anthonyf/Documents/EvoZeus-cluster/10-repos/evozeus-factor-lab status --short --branch
```

当前已知状态：

```text
## codex/docs/20260619-factor-contract-structure...origin/codex/docs/20260619-factor-contract-structure
 M SKILL.md
```

## 最终验证

运行：

```bash
python -m pytest -q
python scripts/validate_official_factor_spec.py factors/*/spec.json
rg -n "evozeus-community|五个 repo|5 个 repo" README.md SKILL.md docs/architecture/factor-system-concepts.md
rg -n "Direct gates:.*tool-failure" SKILL.md
```

预期：

```text
测试通过
spec 校验通过
旧 direct gate / 旧 repo 名 / 五仓总设计口径不再出现
```
