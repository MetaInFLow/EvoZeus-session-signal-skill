from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_factor_module(slug: str):
    path = ROOT / "factors" / slug / "factor.py"
    spec = importlib.util.spec_from_file_location(f"official_factor_{slug.replace('-', '_')}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load official factor: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RepeatedRequestFactor = _load_factor_module("repeated-request").RepeatedRequestFactor
ToolFailureFrequencyFactor = _load_factor_module("tool-failure-frequency").ToolFailureFrequencyFactor
KeySentenceTrendsFactor = _load_factor_module("key-sentence-trends").KeySentenceTrendsFactor
SemanticPhraseClustersFactor = _load_factor_module("semantic-phrase-clusters").SemanticPhraseClustersFactor
TaskCompletionFactor = _load_factor_module("task-completion").TaskCompletionFactor
UserInputSentimentFactor = _load_factor_module("user-input-sentiment").UserInputSentimentFactor
SessionResourceUsageFactor = _load_factor_module("session-resource-usage").SessionResourceUsageFactor


class OfficialFactorsTest(unittest.TestCase):
    def test_minimum_official_factor_set_exists(self) -> None:
        factor_slugs = {path.name for path in (ROOT / "factors").iterdir() if path.is_dir()}

        self.assertIn("task-completion", factor_slugs)
        self.assertIn("user-input-sentiment", factor_slugs)
        self.assertIn("session-resource-usage", factor_slugs)

    def test_repeated_request_returns_matched_with_evidence_ref(self) -> None:
        session = _load_session("repeated-request")
        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "matched")
        self.assertEqual(result.tags, [{"type": "loop", "value": "repeated-request"}])
        self.assertIn({"ref_id": "user-2", "kind": "user_turn"}, result.evidence_refs)
        self.assertEqual(result.target_type, "session")
        self.assertEqual(result.datasets[0].id, "repeated_request_events")
        self.assertEqual(result.presentations[0].component_ref, "builtin.table.v1")

    def test_repeated_request_detects_semantic_chinese_reask_before_resolution(self) -> None:
        session = {
            "session_id": "repeated-chinese-request",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "review一下这些 factor，看看算法有没有问题"},
                {"id": "assistant-1", "role": "assistant", "text": "我先检查代码和日志。"},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": "再 review 一下这些factor，感觉算法还是不对"},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["scores"]["repeated_request_count"], 1.0)
        self.assertIn({"ref_id": "user-2", "kind": "user_turn"}, result.evidence_refs)
        self.assertEqual(payload["datasets"][0]["records"][0]["first_input_text"], "review一下这些 factor，看看算法有没有问题")
        self.assertEqual(payload["datasets"][0]["records"][0]["repeat_input_text"], "再 review 一下这些factor，感觉算法还是不对")

    def test_repeated_request_ignores_short_continuations(self) -> None:
        session = {
            "session_id": "not-a-repeat",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "开始"},
                {"id": "assistant-1", "role": "assistant", "factor_channel": "assistant_result", "text": "我开始处理。"},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": "继续"},
                {"id": "user-3", "role": "user", "factor_channel": "user_input", "text": "ok"},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")

    def test_repeated_request_ignores_consecutive_long_pasted_request(self) -> None:
        long_text = "请 review 这个 factor " + "非常长的背景材料" * 500
        session = {
            "session_id": "long-repeat-request",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": long_text},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": long_text},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)
        self.assertEqual(result.status, "not_matched")

    def test_repeated_request_does_not_treat_follow_up_correction_as_repeat(self) -> None:
        session = {
            "session_id": "follow-up-correction-not-repeat",
            "events": [
                {
                    "id": "user-1",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "删掉本地的 .evozeus，测试一下加入 EvoZeus 的流程",
                },
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "text": "我会先删除本地目录，再跑加入流程。",
                },
                {
                    "id": "user-2",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "vercel 现在部署了一个历史版本，应该是橙色的一个",
                },
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")

    def test_repeated_request_requires_assistant_response_between_user_turns(self) -> None:
        session = {
            "session_id": "mirrored-consecutive-user-turns",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "把项目拉起来"},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": "tauri 跑起来我看下"},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")

    def test_repeated_request_keeps_unresolved_intent_across_task_close(self) -> None:
        session = {
            "session_id": "reask-across-task-close",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "hook会注入哪些过程当前？"},
                {"id": "a1", "role": "assistant", "factor_channel": "assistant_result", "text": "我解释一下 Hook。"},
                {"id": "done1", "role": "task_complete", "factor_channel": "assistant_result", "text": "Task complete"},
                {"id": "u2", "role": "user", "factor_channel": "user_input", "text": "告诉我什么情况下会激活什么hook会做什么"},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)
        record = result.as_dict()["datasets"][0]["records"][0]

        self.assertEqual((record["first_event_id"], record["repeat_event_id"]), ("u1", "u2"))

    def test_repeated_request_counts_a_distinct_exact_resend_without_assistant_reply(self) -> None:
        session = {
            "session_id": "exact-resend",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "source_line": 10, "text": "先帮我把文案部分搞明白"},
                {"id": "u2", "role": "user", "factor_channel": "user_input", "source_line": 20, "text": "先帮我把文案部分搞明白"},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)
        record = result.as_dict()["datasets"][0]["records"][0]

        self.assertEqual((record["first_event_id"], record["repeat_event_id"]), ("u1", "u2"))

    def test_repeated_request_does_not_turn_a_recurring_workflow_topic_into_an_unresolved_reask(self) -> None:
        session = {
            "session_id": "workflow-topic-not-reask",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "加入 EvoZeus"},
                {"id": "a1", "role": "assistant", "factor_channel": "assistant_result", "text": "已进入安装流程。"},
                {"id": "u2", "role": "user", "factor_channel": "user_input", "text": "现在测试安装、注册、开始使用"},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")

    def test_repeated_request_treats_a_detailed_new_direction_as_refinement(self) -> None:
        session = {
            "session_id": "detailed-refinement-not-reask",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "这个页面没有呈现清楚产品定位。"},
                {"id": "a1", "role": "assistant", "factor_channel": "assistant_result", "text": "我会重写定位。"},
                {
                    "id": "u2",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "还是没体现重点，是在持续使用中从种子进化成成品。你要解释为什么能做到、和其他产品有什么不同。我希望强调协同进化，让每个使用者的纠偏汇总起来。",
                },
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")

    def test_repeated_request_ignores_image_payload_and_mirrored_user_event(self) -> None:
        session = {
            "session_id": "image-payload-not-repeat",
            "events": [
                {
                    "id": "2026-06-01T00:00:00Z#L10",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": '[{"image_url":"data:image/png;base64,' + "A" * 180 + '"}]',
                },
                {
                    "id": "2026-06-01T00:00:00Z#L11",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": '[{"image_url":"data:image/png;base64,' + "B" * 180 + '"}]',
                },
                {
                    "id": "2026-06-01T00:00:00Z#L20",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "## My request for Codex:\n检查这个页面为什么错位",
                },
                {
                    "id": "2026-06-01T00:00:00Z#L21",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "# Files mentioned by the user:\n\n## My request for Codex:\n检查这个页面为什么错位",
                },
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")

    def test_tool_failure_frequency_returns_bar_chart_dataset(self) -> None:
        session = _load_session("tool-failure-frequency")
        result = ToolFailureFrequencyFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "frequency_distribution")
        self.assertEqual(payload["datasets"][0]["records"][0]["tool_name"], "exec_command")
        self.assertEqual(payload["datasets"][0]["records"][0]["count"], 1)
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.bar_chart.v1")
        self.assertEqual(payload["presentations"][0]["bindings"]["x"], "tool_name")
        self.assertEqual(payload["presentations"][0]["bindings"]["y"], "count")

    def test_tool_failure_frequency_uses_structured_tool_result_status(self) -> None:
        session = {
            "session_id": "tool-result-status-failure",
            "events": [
                {
                    "id": "tool-1",
                    "role": "tool",
                    "tool_name": "exec_command",
                    "text": "",
                    "tool_result": {"exit_code": 1, "stderr": "permission denied"},
                },
                {
                    "id": "tool-2",
                    "role": "tool",
                    "tool_name": "exec_command",
                    "text": "",
                    "tool_result": {"status": "success", "exit_code": 0},
                },
            ],
        }

        result = ToolFailureFrequencyFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]

        self.assertEqual(result.status, "matched")
        self.assertEqual(records[0]["tool_name"], "exec_command")
        self.assertEqual(records[0]["count"], 1)
        self.assertIn({"ref_id": "tool-1", "kind": "tool_event"}, result.evidence_refs)

    def test_tool_failure_frequency_ignores_wrapper_outputs_without_failure_status(self) -> None:
        session = {
            "session_id": "wrapper-output-not-failure",
            "events": [
                {
                    "id": "tool-1",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "tool_name": "function_call_output",
                    "text": "function_call_output",
                    "codex_event_type": "function_call_output",
                    "tool_result": {"status": "success", "call_id": "call_1"},
                },
                {
                    "id": "tool-2",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "tool_name": "exec_command",
                    "text": "",
                    "tool_result": {"exit_code": 2, "stderr": "pytest failed"},
                },
            ],
        }

        result = ToolFailureFrequencyFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]

        self.assertEqual(result.status, "matched")
        self.assertEqual(
            records,
            [
                {
                    "tool_name": "exec_command",
                    "count": 1,
                    "failure_count": 1,
                    "recovered_count": 0,
                    "unrecovered_count": 1,
                    "evidence_count": 1,
                    "sample_event_ids": ["tool-2"],
                }
            ],
        )

    def test_tool_failure_frequency_detects_codex_function_call_output_exit_code(self) -> None:
        session = {
            "session_id": "codex-function-output-failure",
            "events": [
                {
                    "id": "tool-output-1",
                    "role": "tool",
                    "tool_name": "function_call_output",
                    "codex_event_type": "function_call_output",
                    "text": "Chunk ID: abc Wall time: 0.0000 seconds Process exited with code 1 Output: larkcli not found",
                    "tool_result": {"call_id": "call_1", "name": "exec_command"},
                },
                {
                    "id": "tool-output-2",
                    "role": "tool",
                    "tool_name": "function_call_output",
                    "codex_event_type": "function_call_output",
                    "text": "Chunk ID: def Wall time: 0.0000 seconds Process exited with code 0 Output: ok",
                    "tool_result": {"call_id": "call_2", "name": "exec_command"},
                },
            ],
        }

        result = ToolFailureFrequencyFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]

        self.assertEqual(result.status, "matched")
        self.assertEqual(records[0]["tool_name"], "exec_command")
        self.assertEqual(records[0]["count"], 1)
        self.assertIn({"ref_id": "tool-output-1", "kind": "tool_event"}, result.evidence_refs)

    def test_tool_failure_frequency_pairs_call_id_and_marks_recovered_failure(self) -> None:
        session = {
            "session_id": "paired-recovered-failure",
            "events": [
                {
                    "id": "call-1",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "tool_name": "exec_command",
                    "tool_result": {"call_id": "c1", "name": "exec_command"},
                    "text": "pytest -q",
                },
                {
                    "id": "output-1",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "tool_name": "function_call_output",
                    "codex_event_type": "function_call_output",
                    "tool_result": {"call_id": "c1", "exit_code": 1},
                    "text": "Process exited with code 1",
                },
                {
                    "id": "call-2",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "tool_name": "exec_command",
                    "tool_result": {"call_id": "c2", "name": "exec_command"},
                    "text": "pytest -q",
                },
                {
                    "id": "output-2",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "tool_name": "function_call_output",
                    "codex_event_type": "function_call_output",
                    "tool_result": {"call_id": "c2", "status": "success", "exit_code": 0},
                    "text": "Process exited with code 0",
                },
            ],
        }

        result = ToolFailureFrequencyFactor().evaluate(session)
        record = result.as_dict()["datasets"][0]["records"][0]

        self.assertEqual(record["tool_name"], "exec_command")
        self.assertEqual(record["failure_count"], 1)
        self.assertEqual(record["recovered_count"], 1)
        self.assertEqual(record["unrecovered_count"], 0)

    def test_key_sentence_trends_returns_line_and_heatmap_presentations(self) -> None:
        session = _load_session("key-sentence-trends")
        result = KeySentenceTrendsFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "key_sentence_trend")
        self.assertEqual(payload["datasets"][0]["shape"], "time_series")
        self.assertIn("chat_role", payload["datasets"][0]["schema"])
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.line_chart.v1")
        self.assertEqual(payload["presentations"][1]["component_ref"], "builtin.heatmap.v1")

    def test_key_sentence_trends_segments_candidates_by_chat_role(self) -> None:
        session = {
            "session_id": "key-sentence-role-segments",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "timestamp": "2026-06-18T08:00:00Z", "text": "检查日志"},
                {"id": "assistant-1", "role": "assistant", "factor_channel": "assistant_result", "timestamp": "2026-06-18T08:01:00Z", "text": "运行测试"},
            ],
        }

        result = KeySentenceTrendsFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]
        by_role = {(record["chat_role"], record["cluster_label"]) for record in records}

        self.assertIn(("user", "检查日志"), by_role)
        self.assertNotIn(("assistant", "运行测试"), by_role)

    def test_key_sentence_trends_clusters_repeated_user_requests(self) -> None:
        session = {
            "session_id": "key-sentence-real-requests",
            "events": [
                {"id": "user-1", "role": "user", "timestamp": "2026-06-18T08:00:00Z", "text": "不要改文件，只读审查"},
                {"id": "user-2", "role": "user", "timestamp": "2026-06-19T08:00:00Z", "text": "请只读不改文件，输出具体文件路径和建议"},
                {"id": "assistant-1", "role": "assistant", "timestamp": "2026-06-19T08:01:00Z", "text": "收到。"},
            ],
        }

        result = KeySentenceTrendsFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]
        labels = {record["cluster_label"] for record in records}

        self.assertEqual(result.status, "matched")
        self.assertIn("不要改文件", labels)
        self.assertIn("只读审查", labels)

    def test_key_sentence_trends_extracts_dependency_like_constraints(self) -> None:
        session = {
            "session_id": "key-sentence-dependency-relations",
            "events": [
                {
                    "id": "user-1",
                    "role": "user",
                    "timestamp": "2026-06-18T08:00:00Z",
                    "text": "麻烦先检查数据库迁移，不要删除数据库",
                },
                {
                    "id": "user-2",
                    "role": "user",
                    "timestamp": "2026-06-19T08:00:00Z",
                    "text": "请别删数据库，输出回滚建议",
                },
            ],
        }

        result = KeySentenceTrendsFactor().evaluate(session)

        self.assertEqual(result.status, "matched")
        records = result.as_dict()["datasets"][0]["records"]
        counts: dict[str, int] = {}
        for record in records:
            counts[record["cluster_label"]] = counts.get(record["cluster_label"], 0) + record["count"]

        self.assertEqual(counts["不要删除数据库"], 2)
        self.assertIn("输出回滚建议", counts)

    def test_key_sentence_trends_distinguishes_questions_capability_gaps_and_constraints(self) -> None:
        session = {
            "session_id": "key-sentence-negation-boundaries",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "能不能用动画"},
                {"id": "u2", "role": "user", "factor_channel": "user_input", "text": "这个 skill 不能引导用户主动注册并推进下一步"},
                {"id": "u3", "role": "user", "factor_channel": "user_input", "text": "然后无法应用到 skill 开发的就剔除"},
            ],
        }

        result = KeySentenceTrendsFactor().evaluate(session)
        records = {(record["cluster_label"], record["relation_type"]) for record in result.as_dict()["datasets"][0]["records"]}

        self.assertIn(("能不能用动画", "action_request"), records)
        self.assertIn(("引导用户主动注册并推进下一步", "action_request"), records)
        self.assertIn(("无法应用到 skill 开发的就剔除", "negative_constraint"), records)

    def test_key_sentence_trends_keeps_natural_request_around_a_url(self) -> None:
        session = {
            "session_id": "key-sentence-url-request",
            "events": [
                {
                    "id": "u1",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "https://example.com/hooks 这个是 hook 实现，看看现在 wrapper 是怎么增加 hook 机制的",
                }
            ],
        }

        result = KeySentenceTrendsFactor().evaluate(session)
        records = {(record["cluster_label"], record["relation_type"]) for record in result.as_dict()["datasets"][0]["records"]}

        self.assertIn(("看看现在 wrapper 是怎么增加 hook 机制的", "action_request"), records)

    def test_semantic_phrase_clusters_groups_run_project_variants_and_excludes_report(self) -> None:
        session = {
            "session_id": "semantic-run-project",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "把项目拉起来"},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": "tauri 跑起来我看下"},
                {"id": "user-3", "role": "user", "factor_channel": "user_input", "text": "启动 dev server"},
                {"id": "user-4", "role": "user", "factor_channel": "user_input", "text": "跑一下这个项目"},
                {"id": "user-5", "role": "user", "factor_channel": "user_input", "text": "把报告拉起来看下"},
                {"id": "user-6", "role": "user", "factor_channel": "user_input", "text": "我现在要开项目启动会"},
                {"id": "user-7", "role": "user", "factor_channel": "user_input", "text": "可以直接在应用内实时预览运行效果"},
                {"id": "user-8", "role": "user", "factor_channel": "user_input", "text": "现在两个 app 都运行起来了"},
                {"id": "user-9", "role": "user", "factor_channel": "user_input", "text": "写一下如何启动项目的指南"},
            ],
        }

        result = SemanticPhraseClustersFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]

        self.assertEqual(result.status, "matched")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["cluster_id"], "intent.run_project")
        self.assertEqual(records[0]["turn_count"], 4)
        self.assertNotIn("把报告拉起来看下", records[0]["variants"])
        self.assertNotIn("我现在要开项目启动会", records[0]["variants"])
        self.assertNotIn("可以直接在应用内实时预览运行效果", records[0]["variants"])

    def test_semantic_phrase_clusters_groups_factor_review_rephrases(self) -> None:
        session = {
            "session_id": "semantic-review-factors",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "review一下这些 factor，看看算法有没有问题"},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": "再检查一下这些 factor，算法感觉还是不对"},
            ],
        }

        result = SemanticPhraseClustersFactor().evaluate(session)
        record = result.as_dict()["datasets"][0]["records"][0]

        self.assertEqual(record["cluster_id"], "intent.review_factors")
        self.assertEqual(record["turn_count"], 2)

    def test_semantic_phrase_clusters_groups_product_feedback_and_output_preferences(self) -> None:
        session = {
            "session_id": "semantic-product-feedback",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "这个页面没有呈现清楚我们的一句话定位、功能"},
                {"id": "u2", "role": "user", "factor_channel": "user_input", "text": "还是都看不懂，都不像在说人话"},
                {"id": "u3", "role": "user", "factor_channel": "user_input", "text": "这个文档不要那么多背景，我只要结果"},
                {"id": "u4", "role": "user", "factor_channel": "user_input", "text": "不要一大段文字，用词要直接"},
            ],
        }

        result = SemanticPhraseClustersFactor().evaluate(session)
        records = {record["cluster_id"]: record for record in result.as_dict()["datasets"][0]["records"]}

        self.assertEqual(records["intent.clarify_positioning"]["turn_count"], 2)
        self.assertEqual(records["intent.clarify_positioning"]["label"], "讲清楚产品定位")
        self.assertEqual(records["intent.concise_supplier_output"]["turn_count"], 2)
        self.assertIn("不要那么多背景，我只要结果", records["intent.concise_supplier_output"]["variants"])

    def test_task_completion_returns_verdict_dataset(self) -> None:
        session = _load_session("task-completion")
        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "task_completion_verdict")
        self.assertEqual(payload["datasets"][0]["records"][0]["verdict"], "completed")
        self.assertEqual(payload["scores"]["task_completion_score"], 1.0)
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.table.v1")

    def test_task_completion_prefers_later_blocker_over_early_completion_claim(self) -> None:
        session = {
            "session_id": "completion-later-blocker",
            "events": [
                {"id": "assistant-1", "role": "assistant", "text": "已完成初步修改。"},
                {"id": "tool-1", "role": "tool", "text": "", "tool_result": {"status": "failed", "stderr": "tests are still failing"}},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "not_matched")
        self.assertEqual(payload["statistics"]["verdict"], "not_completed")
        self.assertEqual(payload["scores"]["task_completion_score"], 0.0)
        self.assertIn({"ref_id": "tool-1", "kind": "tool"}, result.evidence_refs)

    def test_task_completion_accepts_codex_task_complete_event(self) -> None:
        session = {
            "session_id": "codex-task-complete",
            "events": [
                {"id": "event-1", "role": "task_complete", "text": "Task complete"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)

        self.assertEqual(result.status, "matched")
        self.assertEqual(result.as_dict()["statistics"]["verdict"], "completed")

    def test_task_completion_prefers_runtime_close_over_assistant_claim(self) -> None:
        session = {
            "session_id": "claimed-then-closed",
            "events": [
                {"id": "assistant-1", "role": "assistant", "text": "已完成文档修改。"},
                {"id": "closed-1", "role": "task_complete", "text": "Task complete"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)

        self.assertEqual(result.as_dict()["statistics"]["verification"], "runtime_closed")
        self.assertEqual(result.evidence_refs, [{"ref_id": "closed-1", "kind": "task_complete"}])

    def test_task_completion_only_uses_evidence_from_the_last_user_task(self) -> None:
        session = {
            "session_id": "last-user-task-epoch",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "修复测试"},
                {
                    "id": "t1",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "text": "3 passed",
                    "tool_result": {"status": "success"},
                },
                {"id": "u2", "role": "user", "factor_channel": "user_input", "text": "再解释一下设计意图"},
                {"id": "a2", "role": "assistant", "factor_channel": "assistant_result", "text": "解释已整理完成。"},
                {"id": "done2", "role": "task_complete", "factor_channel": "assistant_result", "text": "Task complete"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)

        self.assertEqual(result.as_dict()["statistics"]["verification"], "runtime_closed")
        self.assertEqual(result.evidence_refs, [{"ref_id": "done2", "kind": "task_complete"}])

    def test_task_completion_accepts_release_view_as_structured_verification(self) -> None:
        session = {
            "session_id": "release-view-verification",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "发布 release"},
                {
                    "id": "call1",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "text": '{"cmd":"gh release view --json tagName,url"}',
                    "tool_result": {"call_id": "c1"},
                },
                {
                    "id": "result1",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "text": "Process exited with code 0\n{\"tagName\":\"v1.0.0\"}",
                    "tool_result": {"call_id": "c1", "exit_code": 0},
                },
            ],
        }

        result = TaskCompletionFactor().evaluate(session)

        self.assertEqual(result.as_dict()["statistics"]["verification"], "verified")
        self.assertEqual(result.evidence_refs, [{"ref_id": "result1", "kind": "tool"}])

    def test_task_completion_rejects_release_view_with_masked_command_error(self) -> None:
        session = {
            "session_id": "masked-release-view-error",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "发布 release"},
                {
                    "id": "call1",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "text": '{"cmd":"gh release view --json isLatest || true"}',
                    "tool_result": {"call_id": "c1"},
                },
                {
                    "id": "result1",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "text": "Process exited with code 0\nUnknown JSON field: isLatest",
                    "tool_result": {"call_id": "c1", "exit_code": 0},
                },
                {"id": "done1", "role": "task_complete", "text": "Task complete"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)

        self.assertEqual(result.as_dict()["statistics"]["verification"], "runtime_closed")

    def test_task_completion_does_not_verify_from_wrapper_call_text(self) -> None:
        session = {
            "session_id": "wrapper-call-is-not-proof",
            "events": [
                {
                    "id": "call-1",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "codex_event_type": "custom_tool_call",
                    "text": 'tools.exec_command({"cmd":"git diff --check"})',
                    "tool_result": {"status": "completed", "call_id": "c1"},
                },
                {
                    "id": "closed-1",
                    "role": "task_complete",
                    "factor_channel": "assistant_result",
                    "text": "Task complete",
                },
            ],
        }

        result = TaskCompletionFactor().evaluate(session)

        self.assertEqual(result.as_dict()["statistics"]["verification"], "runtime_closed")
        self.assertEqual(result.evidence_refs, [{"ref_id": "closed-1", "kind": "task_complete"}])

    def test_task_completion_uses_nlp_blocked_signal_from_final_assistant(self) -> None:
        session = {
            "session_id": "completion-blocked-final",
            "events": [
                {"id": "assistant-1", "role": "assistant", "factor_channel": "assistant_result", "text": "我无法继续执行，因为缺少必要权限，需要你提供访问方式。"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "not_matched")
        self.assertEqual(payload["statistics"]["verdict"], "blocked")
        self.assertEqual(payload["scores"]["task_completion_score"], 0.25)

    def test_task_completion_ignores_intermediate_progress_as_blocked(self) -> None:
        session = {
            "session_id": "intermediate-progress-not-blocked",
            "events": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "text": "当前工作区相关真实记录一共有 34 条，现在我先对一条真实 session 跑 7 个 official factors 做 smoke，再批量跑剩下的。",
                },
                {
                    "id": "assistant-2",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "text": "我会继续处理并汇总结果。",
                },
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "not_matched")
        self.assertEqual(payload["statistics"]["verdict"], "unknown")
        self.assertEqual(payload["scores"]["task_completion_score"], 0.0)

    def test_task_completion_treats_final_created_summary_as_completed(self) -> None:
        session = {
            "session_id": "guide-created-completed",
            "events": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "text": "Guide Created - Added `AGENTS.md` with a contributor guide.",
                }
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["statistics"]["verdict"], "completed")

    def test_task_completion_does_not_treat_instructional_advice_as_completed(self) -> None:
        session = {
            "session_id": "instructional-advice-unknown",
            "events": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "text": "两台设备已配对，无需再次 pair。直接启动两个模拟器，然后查看数据。",
                }
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "not_matched")
        self.assertEqual(payload["statistics"]["verdict"], "unknown")

    def test_task_completion_uses_successful_test_output_as_verified_completion(self) -> None:
        session = {
            "session_id": "verified-test-completion",
            "events": [
                {
                    "id": "tool-call",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "tool_name": "exec_command",
                    "tool_result": {"call_id": "call-1", "name": "exec_command"},
                    "text": "pytest -q",
                },
                {
                    "id": "tool-output",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "tool_name": "function_call_output",
                    "tool_result": {"call_id": "call-1", "status": "success", "exit_code": 0},
                    "text": "12 passed",
                },
                {"id": "assistant-final", "role": "assistant", "factor_channel": "assistant_result", "text": "修复完成，测试通过。"},
                {"id": "task-complete", "role": "task_complete", "factor_channel": "assistant_result", "text": "Task complete"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(payload["statistics"]["verdict"], "completed")
        self.assertEqual(payload["statistics"]["verification"], "verified")
        self.assertEqual(result.evidence_refs, [{"ref_id": "tool-output", "kind": "tool"}])

    def test_task_completion_user_rejection_overrides_assistant_completion_claim(self) -> None:
        session = {
            "session_id": "user-rejected-completion",
            "events": [
                {"id": "assistant-1", "role": "assistant", "factor_channel": "assistant_result", "text": "已经改好了。"},
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "不对，改动太大了。"},
            ],
        }

        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "not_matched")
        self.assertEqual(payload["statistics"]["verdict"], "not_completed")
        self.assertEqual(payload["statistics"]["verification"], "user_rejected")
        self.assertEqual(result.evidence_refs, [{"ref_id": "user-1", "kind": "user"}])

    def test_user_input_sentiment_returns_distribution_and_turn_rows(self) -> None:
        session = _load_session("user-input-sentiment")
        result = UserInputSentimentFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "user_sentiment")
        self.assertEqual(payload["datasets"][1]["semantic_type"], "frequency_distribution")
        self.assertEqual(payload["datasets"][0]["records"][0]["sentiment_kind"], "problem_report")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.bar_chart.v1")

    def test_user_input_sentiment_ignores_context_and_detects_correction_frustration(self) -> None:
        session = {
            "session_id": "codex-user-correction-sentiment",
            "events": [
                {
                    "id": "context-1",
                    "role": "user",
                    "factor_channel": "context",
                    "text": "# AGENTS.md instructions\n<environment_context><cwd>/tmp/project</cwd></environment_context>",
                },
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "不对，改动太大了，排版不要大变化"},
            ],
        }

        result = UserInputSentimentFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(payload["statistics"]["user_turn_count"], 1)
        self.assertEqual(payload["statistics"]["dominant_sentiment_kind"], "correction_request")
        self.assertEqual(payload["datasets"][0]["records"][0]["sentiment_kind"], "correction_request")
        self.assertEqual(payload["datasets"][0]["records"][0]["input_text"], "不对，改动太大了，排版不要大变化")
        self.assertEqual(payload["datasets"][0]["records"][0]["matched_excerpt"], "不对，改动太大了，排版不要大变化")

    def test_user_input_sentiment_handles_long_pasted_request(self) -> None:
        session = {
            "session_id": "long-sentiment-request",
            "events": [
                {
                    "id": "user-1",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "这个结果不行，刚才还在报错。" + "很长的背景材料" * 500,
                }
            ],
        }

        result = UserInputSentimentFactor().evaluate(session)

        self.assertEqual(result.status, "matched")
        self.assertEqual(result.as_dict()["datasets"][0]["records"][0]["sentiment_kind"], "problem_report")

    def test_user_input_sentiment_keeps_plain_tasks_neutral(self) -> None:
        session = {
            "session_id": "plain-task-neutral",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "上传到当前分支现在的代码"},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": "Generate a file named AGENTS.md that serves as a contributor guide"},
            ],
        }

        result = UserInputSentimentFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]

        self.assertEqual(result.status, "not_matched")
        self.assertEqual({record["sentiment_kind"] for record in records}, {"neutral_request"})
        self.assertEqual(result.evidence_refs, [])

    def test_user_input_sentiment_treats_negated_failure_as_correction(self) -> None:
        session = {
            "session_id": "negated-failure-correction",
            "events": [
                {
                    "id": "user-1",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "但实际上 fastbuild 没有失败，已经成功跑完了。",
                }
            ],
        }

        result = UserInputSentimentFactor().evaluate(session)
        record = result.as_dict()["datasets"][0]["records"][0]

        self.assertEqual(result.status, "matched")
        self.assertEqual(record["sentiment_kind"], "correction_request")
        self.assertEqual(result.evidence_refs, [{"ref_id": "user-1", "kind": "user_turn"}])

    def test_user_input_sentiment_does_not_match_bug_inside_debugging(self) -> None:
        session = {
            "session_id": "debugging-is-not-bug-report",
            "events": [
                {
                    "id": "user-1",
                    "role": "user",
                    "factor_channel": "user_input",
                    "text": "请使用 systematic-debugging 排查，并调用 node_repl MCP",
                }
            ],
        }

        result = UserInputSentimentFactor().evaluate(session)

        self.assertEqual(result.status, "not_matched")
        self.assertEqual(result.evidence_refs, [])

    def test_user_input_sentiment_separates_chinese_corrections_from_pure_dissatisfaction(self) -> None:
        session = {
            "session_id": "chinese-feedback-boundaries",
            "events": [
                {"id": "u1", "role": "user", "factor_channel": "user_input", "text": "还是没体现重点，你要讲清楚差异。"},
                {"id": "u2", "role": "user", "factor_channel": "user_input", "text": "太长了，细节应该放到 Skill 里。"},
                {"id": "u3", "role": "user", "factor_channel": "user_input", "text": "不要那么多背景，我只要结果。"},
                {"id": "u4", "role": "user", "factor_channel": "user_input", "text": "这段不像真人写的，AI 味很重。"},
                {"id": "u5", "role": "user", "factor_channel": "user_input", "text": "还是都看不懂，也不像在说人话。"},
                {"id": "u6", "role": "user", "factor_channel": "user_input", "text": "方向还是很蠢很普通。"},
            ],
        }

        result = UserInputSentimentFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]

        assert [(record["event_id"], record["sentiment_kind"]) for record in records] == [
            ("u1", "correction_request"),
            ("u2", "correction_request"),
            ("u3", "correction_request"),
            ("u4", "correction_request"),
            ("u5", "dissatisfaction"),
            ("u6", "dissatisfaction"),
        ]

    def test_session_resource_usage_extracts_tools_skills_and_mcp(self) -> None:
        session = _load_session("session-resource-usage")
        result = SessionResourceUsageFactor().evaluate(session)
        payload = result.as_dict()

        resource_keys = {record["resource_key"] for record in payload["datasets"][0]["records"]}

        self.assertEqual(result.status, "matched")
        self.assertIn("tool:exec_command", resource_keys)
        self.assertIn("skill:systematic-debugging", resource_keys)
        self.assertIn("mcp:node_repl", resource_keys)
        self.assertEqual(payload["datasets"][0]["semantic_type"], "session_resource_usage")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.bar_chart.v1")

    def test_session_resource_usage_extracts_resources_from_codex_text(self) -> None:
        session = {
            "session_id": "codex-resource-text",
            "events": [
                {"id": "assistant-1", "role": "assistant", "text": "我会用 $systematic-debugging 和 mcp__node_repl__js 排查。"},
                {"id": "tool-1", "role": "tool", "tool_name": "mcp__node_repl__js", "text": "ok"},
                {"id": "tool-2", "role": "tool", "text": ""},
            ],
        }

        result = SessionResourceUsageFactor().evaluate(session)
        resource_keys = {record["resource_key"] for record in result.as_dict()["datasets"][0]["records"]}

        self.assertIn("skill:systematic-debugging", resource_keys)
        self.assertIn("mcp:node_repl", resource_keys)
        self.assertIn("tool:mcp__node_repl__js", resource_keys)
        self.assertNotIn("tool:unknown_tool", resource_keys)

    def test_session_resource_usage_excludes_skill_noise_from_codex_context(self) -> None:
        session = {
            "session_id": "codex-skill-noise",
            "events": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "text": "我会使用 $systematic-debugging。环境里有 $HOME $CODEX_HOME $PWCLI $SkillName $1 $2。",
                },
            ],
        }

        result = SessionResourceUsageFactor().evaluate(session)
        datasets = {dataset["id"]: dataset["records"] for dataset in result.as_dict()["datasets"]}
        resource_keys = {record["resource_key"] for record in datasets["session_resource_usage"]}
        diagnostics = {record["resource_name"] for record in datasets["session_resource_diagnostics"]}

        self.assertIn("skill:systematic-debugging", resource_keys)
        self.assertNotIn("skill:HOME", resource_keys)
        self.assertNotIn("skill:CODEX_HOME", resource_keys)
        self.assertNotIn("skill:PWCLI", resource_keys)
        self.assertNotIn("skill:SkillName", resource_keys)
        self.assertIn("HOME", diagnostics)

    def test_session_resource_usage_counts_tool_call_not_wrapper_output(self) -> None:
        session = {
            "session_id": "dedupe-tool-call-output",
            "events": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "factor_channel": "assistant_result",
                    "skill_name": "systematic-debugging",
                    "text": "我会使用 $systematic-debugging 和 mcp__node_repl__js。",
                },
                {
                    "id": "call-1",
                    "role": "tool",
                    "factor_channel": "tool_usage",
                    "tool_name": "mcp__node_repl__js",
                    "tool_result": {"call_id": "c1", "name": "mcp__node_repl__js"},
                    "text": "{}",
                },
                {
                    "id": "output-1",
                    "role": "tool",
                    "factor_channel": "tool_result",
                    "tool_name": "function_call_output",
                    "tool_result": {"call_id": "c1", "status": "success"},
                    "text": "ok",
                },
            ],
        }

        result = SessionResourceUsageFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]
        counts = {(record["resource_type"], record["resource_name"]): record["count"] for record in records}

        self.assertEqual(counts[("skill", "systematic-debugging")], 1)
        self.assertEqual(counts[("tool", "mcp__node_repl__js")], 1)
        self.assertEqual(counts[("mcp", "node_repl")], 1)


def _load_session(slug: str) -> dict:
    return json.loads((ROOT / "factors" / slug / "session.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
