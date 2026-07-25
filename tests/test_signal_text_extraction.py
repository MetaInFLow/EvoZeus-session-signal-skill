from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evozeus_session_signal_skill.nlp import classify_signal_text, direct_user_events, is_direct_user_input, signal_text


def test_signal_text_extracts_request_after_codex_marker_and_drops_code_block():
    message = (
        "# Files mentioned by the user:\n"
        "## codex-clipboard-demo.png: /var/folders/demo/codex-clipboard-demo.png\n\n"
        "## My request for Codex:\n"
        "帮我判断这个 JSON 哪里失败\n"
        "```json\n"
        '{"status":"error","payload":{"items":[1,2,3]}}\n'
        "```"
    )

    blocks = classify_signal_text({"role": "user", "factor_channel": "user_input", "text": message})

    assert signal_text(message) == "帮我判断这个 JSON 哪里失败"
    assert ("request_text", True) in {(block.block_type, block.should_feed_factor) for block in blocks}
    assert ("code_paste", False) in {(block.block_type, block.should_feed_factor) for block in blocks}


def test_signal_text_keeps_natural_prefix_and_drops_log_paste():
    message = "\n".join(
        [
            "帮我 debug 这个失败",
            "Traceback (most recent call last):",
            "  File \"/tmp/app.py\", line 1, in <module>",
            "Exception: failed to connect",
            "ERROR failed",
            "ERROR failed",
            "ERROR failed",
        ]
    )

    blocks = classify_signal_text({"role": "user", "factor_channel": "user_input", "text": message})

    assert signal_text(message) == "帮我 debug 这个失败"
    assert any(block.block_type == "log_paste" and not block.should_feed_factor for block in blocks)


def test_signal_text_drops_image_payload():
    message = '[{"image_url":"data:image/png;base64,' + "A" * 200 + '"}]'

    blocks = classify_signal_text({"role": "user", "factor_channel": "user_input", "text": message})

    assert signal_text(message) == ""
    assert blocks[0].block_type == "media_payload"
    assert blocks[0].should_feed_factor is False


def test_signal_text_marks_context_event_as_non_factor_input():
    blocks = classify_signal_text(
        {
            "role": "user",
            "factor_channel": "context",
            "text": "# AGENTS.md instructions\n<environment_context><cwd>/tmp/project</cwd></environment_context>",
        }
    )

    assert signal_text({"role": "user", "factor_channel": "context", "text": "检查下"}) == ""
    assert blocks[0].block_type == "context_block"
    assert blocks[0].should_feed_factor is False


def test_direct_user_input_accepts_structurally_confirmed_codex_user_message():
    event = {
        "role": "user",
        "factor_channel": "user_input",
        "message_scope": "direct_user",
        "session_thread_source": "user",
        "codex_user_origin": "event_msg_mirror",
        "text": "不要只给结果，要给判断依据和验收标准。",
    }

    assert is_direct_user_input(event) is True
    assert signal_text(event) == "不要只给结果，要给判断依据和验收标准。"


def test_direct_user_input_rejects_codex_synthetic_context_even_when_role_is_user():
    event = {
        "role": "user",
        "factor_channel": "user_input",
        "message_scope": "direct_user",
        "session_thread_source": "user",
        "codex_user_origin": "synthetic_context",
        "text": "<skill><name>product-design:index</name><path>/tmp/SKILL.md</path></skill>",
    }

    assert is_direct_user_input(event) is False
    assert direct_user_events([event]) == []


def test_direct_user_input_rejects_subagent_lineage_without_content_template_match():
    event = {
        "role": "user",
        "factor_channel": "user_input",
        "message_scope": "direct_user",
        "session_thread_source": "subagent",
        "session_source_kind": "subagent",
        "subagent_parent_thread_id": "parent-thread",
        "codex_user_origin": "event_msg_mirror",
        "text": "不要只给结果，要给判断依据、成功标准、验收标准和可验证交付。",
    }

    assert is_direct_user_input(event) is False
    assert direct_user_events([event]) == []


def test_direct_user_input_keeps_legacy_direct_user_event_without_origin_marker():
    event = {
        "role": "user",
        "factor_channel": "user_input",
        "message_scope": "direct_user",
        "text": "看下这个报告是否可信。",
    }

    assert is_direct_user_input(event) is True


def test_direct_user_input_reads_origin_from_nested_metadata():
    event = {
        "role": "user",
        "text": "看看这个报告是否可信。",
        "metadata": {
            "factor_channel": "user_input",
            "message_scope": "direct_user",
            "session_thread_source": "user",
            "codex_user_origin": "event_msg_mirror",
        },
    }

    assert is_direct_user_input(event) is True
