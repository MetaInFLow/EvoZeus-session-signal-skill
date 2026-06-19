# 新建 Official Factor 指南

本指南用于在 `evozeus-factors-official` 中新增一个 official factor。这里的 official 表示“稳定合约样例和官方抽象”，不是业务 pack 的发布入口。

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
  factor.py
  spec.json
  session.json
```

- `factor.py`：可运行 Python factor，实现 `OfficialFactor.evaluate()`。
- `spec.json`：可被 schema 和 validator 独立检查的官方 spec。
- `session.json`：脱敏 test vector 输入，不能包含 private session 或客户数据。

`factor.py` 中的 Python spec 常量必须和 `spec.json` 保持同步。

## 命名规则

- 目录名：`task-completion`、`user-input-sentiment` 这种 kebab-case。
- `factor_id`：使用 `official.<factor-slug>`，例如 `official.task-completion`。
- Python class：使用 PascalCase 并以 `Factor` 结尾，例如 `TaskCompletionFactor`。
- Python spec 常量：使用大写 snake case，例如 `OFFICIAL_TASK_COMPLETION_SPEC`。
- dataset id / presentation id：使用 snake_case，例如 `task_completion_verdict`。

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

先明确 factor 要分析什么对象，再决定输入范围：

- 只分析单次对话：`accepted_input_kinds = ["session"]`。
- 需要跨会话聚合：加入 `project` 或 `scan_record_set`。
- 依赖历史 factor 结果：在 `prior_result_policy` 中说明，必要时使用 `prior_results`。

常见字段：

- `events[].id`：用于 evidence ref。
- `events[].role`：区分 user / assistant / tool / system。
- `events[].text`：用于文本信号识别。
- `events[].timestamp`：用于趋势、时间桶或 session timeline。
- `events[].tool_name`：用于 tool 使用和失败统计。

## 输出契约设计

Factor 输出统一使用 `OfficialFactorResult`。设计输出时先区分三层：

- `scores` / `statistics`：小型数值和摘要，适合快速判断。
- `datasets`：结构化 read model，适合落账、查询和可视化。
- `presentations`：展示建议，只引用 component ref，不携带前端代码。

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

from evozeus_factors_official import OfficialFactor, OfficialFactorResult


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
- [ ] `factor.py` 中的 spec 常量和 `spec.json` 同步。
- [ ] `title_i18n` / `summary_i18n` 同时包含 `zh-CN` 和 `en-US`。
- [ ] `input_contract` 明确 accepted input kinds、target types、record types。
- [ ] `output_contract` 明确 dataset semantic types 和 presentation components。
- [ ] `matched` 分支返回稳定 `evidence_refs`。
- [ ] `session.json` 是脱敏 test vector。
- [ ] 单元测试覆盖 status、dataset、presentation、evidence。
- [ ] `python3 -m unittest discover -s tests` 通过。
- [ ] `python3 scripts/validate_official_factor_spec.py factors/*/spec.json` 通过。

## 常见错误

- 只写 `factor.py`，忘记同步 `spec.json`。
- 只写中文 `summary`，漏掉 `summary_i18n.en-US`。
- `matched` 没有 `evidence_refs`，会被 `build_result()` 拦截。
- dataset 直接按图表命名，例如 `bar_chart_data`，没有表达业务语义。
- presentation 引用了不存在的 `data_ref`。
- 把前端组件代码、业务 pack 发布信息或真实业务数据放进本 repo。
