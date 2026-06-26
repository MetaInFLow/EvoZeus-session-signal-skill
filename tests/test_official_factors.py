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
UsageSentenceCloudFactor = _load_factor_module("usage-sentence-cloud").UsageSentenceCloudFactor
ToolFailureFrequencyFactor = _load_factor_module("tool-failure-frequency").ToolFailureFrequencyFactor
KeySentenceTrendsFactor = _load_factor_module("key-sentence-trends").KeySentenceTrendsFactor
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

    def test_repeated_request_handles_long_pasted_request_without_expanding_signature(self) -> None:
        long_text = "请 review 这个 factor " + "非常长的背景材料" * 500
        session = {
            "session_id": "long-repeat-request",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": long_text},
                {"id": "user-2", "role": "user", "factor_channel": "user_input", "text": long_text},
            ],
        }

        result = RepeatedRequestFactor().evaluate(session)
        record = result.as_dict()["datasets"][0]["records"][0]

        self.assertEqual(result.status, "matched")
        self.assertLessEqual(len(record["request_signature"]), 120)

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

    def test_usage_sentence_cloud_returns_dataset_and_word_cloud_presentation(self) -> None:
        session = _load_session("usage-sentence-cloud")
        result = UsageSentenceCloudFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["target_type"], "session")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "high_frequency_phrase_set")
        self.assertEqual(payload["datasets"][0]["records"][0]["chat_role"], "user")
        self.assertEqual(payload["datasets"][0]["records"][0]["display_sentence"], "合理利用 subagent")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.word_cloud.v1")
        self.assertEqual(payload["presentations"][0]["bindings"]["word"], "text")
        self.assertEqual(payload["presentations"][0]["bindings"]["weight"], "value")

    def test_usage_sentence_cloud_segments_phrases_by_chat_role(self) -> None:
        session = {
            "session_id": "role-segmented-usage",
            "events": [
                {"id": "user-1", "role": "user", "factor_channel": "user_input", "text": "检查日志，检查日志"},
                {"id": "assistant-1", "role": "assistant", "factor_channel": "assistant_result", "text": "运行测试，运行测试"},
                {"id": "tool-1", "role": "tool", "factor_channel": "tool_result", "text": "pytest failed with exit code 1"},
            ],
        }

        result = UsageSentenceCloudFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]
        by_role = {(record["chat_role"], record["display_sentence"]) for record in records}

        self.assertIn(("user", "检查日志"), by_role)
        self.assertIn(("assistant", "运行测试"), by_role)
        self.assertIn(("tool", "pytest failed with exit code 1"), by_role)

    def test_usage_sentence_cloud_extracts_codex_request_short_sentences(self) -> None:
        session = {
            "session_id": "codex-wrapped-usage-sentences",
            "events": [
                {
                    "id": "context-1",
                    "role": "user",
                    "text": "# AGENTS.md instructions for /tmp/project\n"
                    "<INSTRUCTIONS>项目产出文件默认用中文</INSTRUCTIONS>\n"
                    "<environment_context><cwd>/tmp/project</cwd></environment_context>",
                },
                {
                    "id": "user-1",
                    "role": "user",
                    "text": "# Files mentioned by the user:\n\n"
                    "## codex-clipboard-demo.png: /var/folders/demo/codex-clipboard-demo.png\n\n"
                    "## My request for Codex:\n"
                    "改动太大了，排版不要大变化。\n"
                    "<image name=[Image #1] path=\"/var/folders/demo/codex-clipboard-demo.png\">\n"
                    "</image>",
                },
                {
                    "id": "user-1-mirror",
                    "role": "user",
                    "text": "# Files mentioned by the user:\n\n"
                    "## codex-clipboard-demo.png: /var/folders/demo/codex-clipboard-demo.png\n\n"
                    "## My request for Codex:\n"
                    "改动太大了，排版不要大变化。",
                },
                {
                    "id": "noise-1",
                    "role": "user",
                    "text": "<subagent_notification> {\"agent_path\":\"abc\","
                    "\"status\":{\"completed\":\"README.md\"}} </subagent_notification>",
                },
                {"id": "user-2", "role": "user", "text": "好的，继续。"},
                {"id": "user-3", "role": "user", "text": "继续"},
                {
                    "id": "noise-2",
                    "role": "user",
                    "text": "README.md\npyproject.toml\nartifacts/current.yml\n.venv/\n"
                    "https://example.com\ntext\nproject\nindex\n"
                    "Continue working toward the active thread goal.",
                },
            ],
        }

        result = UsageSentenceCloudFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]
        counts = {record["display_sentence"]: record["count"] for record in records}

        self.assertNotIn("继续", counts)
        self.assertEqual(counts["改动太大了"], 1)
        self.assertEqual(counts["排版不要大变化"], 1)
        self.assertNotIn("README.md", counts)
        self.assertNotIn("https", counts)
        self.assertNotIn("agent_path", counts)
        self.assertNotIn("completed", counts)
        self.assertNotIn("text", counts)
        self.assertNotIn("project", counts)
        self.assertNotIn("index", counts)
        self.assertNotIn("pyproject.toml", counts)
        self.assertNotIn("artifacts/current.yml", counts)
        self.assertNotIn(".venv/", counts)
        self.assertNotIn("Continue working toward the active thread goal.", counts)
        self.assertNotIn("AGENTS.md instructions for /tmp/project", counts)
        self.assertTrue(all("Files mentioned by the user" not in record["display_sentence"] for record in records))
        self.assertTrue(all("image name=" not in record["display_sentence"] for record in records))

    def test_usage_sentence_cloud_keeps_request_text_from_markdown_link(self) -> None:
        session = {
            "session_id": "codex-markdown-link-request",
            "events": [
                {
                    "id": "user-1",
                    "role": "user",
                    "text": "[deanpeters/Product-Manager-Skills.git](https://github.com/deanpeters/Product-Manager-Skills.git)安装这个skill",
                }
            ],
        }

        result = UsageSentenceCloudFactor().evaluate(session)
        records = result.as_dict()["datasets"][0]["records"]
        sentences = {record["display_sentence"] for record in records}

        self.assertEqual(result.status, "matched")
        self.assertIn("安装这个skill", sentences)

    def test_usage_sentence_cloud_drops_long_segments_before_path_regex(self) -> None:
        from evozeus_session_signal_skill import nlp

        class GuardedPathPattern:
            def search(self, value: str):
                if len(value) > 200:
                    raise AssertionError("long text reached path/url regex")
                return None

        original_pattern = nlp.PATH_OR_URL_RE
        nlp.PATH_OR_URL_RE = GuardedPathPattern()  # type: ignore[assignment]
        try:
            session = {
                "session_id": "long-tool-output",
                "events": [
                    {
                        "id": "tool-1",
                        "role": "tool",
                        "factor_channel": "tool_result",
                        "text": "工具输出 " + ("非常长的日志片段" * 1000),
                    }
                ],
            }

            result = UsageSentenceCloudFactor().evaluate(session)
        finally:
            nlp.PATH_OR_URL_RE = original_pattern

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
        self.assertEqual(records, [{"tool_name": "exec_command", "count": 1, "evidence_count": 1, "sample_event_ids": ["tool-2"]}])

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
        self.assertIn(("assistant", "运行测试"), by_role)

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


def _load_session(slug: str) -> dict:
    return json.loads((ROOT / "factors" / slug / "session.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
