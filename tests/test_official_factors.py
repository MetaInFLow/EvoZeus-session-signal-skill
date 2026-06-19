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

    def test_usage_sentence_cloud_returns_dataset_and_word_cloud_presentation(self) -> None:
        session = _load_session("usage-sentence-cloud")
        result = UsageSentenceCloudFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["target_type"], "session")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "high_frequency_phrase_set")
        self.assertEqual(payload["datasets"][0]["records"][0]["display_sentence"], "合理利用 subagent")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.word_cloud.v1")
        self.assertEqual(payload["presentations"][0]["bindings"]["word"], "text")
        self.assertEqual(payload["presentations"][0]["bindings"]["weight"], "value")

    def test_tool_failure_frequency_returns_bar_chart_dataset(self) -> None:
        session = _load_session("tool-failure-frequency")
        result = ToolFailureFrequencyFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "frequency_distribution")
        self.assertEqual(payload["datasets"][0]["records"][0]["tool_name"], "exec_command")
        self.assertEqual(payload["datasets"][0]["records"][0]["count"], 2)
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.bar_chart.v1")
        self.assertEqual(payload["presentations"][0]["bindings"]["x"], "tool_name")
        self.assertEqual(payload["presentations"][0]["bindings"]["y"], "count")

    def test_key_sentence_trends_returns_line_and_heatmap_presentations(self) -> None:
        session = _load_session("key-sentence-trends")
        result = KeySentenceTrendsFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "key_sentence_trend")
        self.assertEqual(payload["datasets"][0]["shape"], "time_series")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.line_chart.v1")
        self.assertEqual(payload["presentations"][1]["component_ref"], "builtin.heatmap.v1")

    def test_task_completion_returns_verdict_dataset(self) -> None:
        session = _load_session("task-completion")
        result = TaskCompletionFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "task_completion_verdict")
        self.assertEqual(payload["datasets"][0]["records"][0]["verdict"], "completed")
        self.assertEqual(payload["scores"]["task_completion_score"], 1.0)
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.table.v1")

    def test_user_input_sentiment_returns_distribution_and_turn_rows(self) -> None:
        session = _load_session("user-input-sentiment")
        result = UserInputSentimentFactor().evaluate(session)
        payload = result.as_dict()

        self.assertEqual(result.status, "matched")
        self.assertEqual(payload["datasets"][0]["semantic_type"], "user_sentiment")
        self.assertEqual(payload["datasets"][1]["semantic_type"], "frequency_distribution")
        self.assertEqual(payload["datasets"][0]["records"][0]["sentiment"], "negative")
        self.assertEqual(payload["presentations"][0]["component_ref"], "builtin.bar_chart.v1")

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


def _load_session(slug: str) -> dict:
    return json.loads((ROOT / "factors" / slug / "session.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
