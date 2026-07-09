"""Agent 能力说明与 Voice prompt 注入测试。"""
from vocamind.tools.capabilities import format_agent_capabilities_for_voice
from vocamind.voice.prompt import assemble_voice_system_prompt


def test_capabilities_mentions_key_abilities():
    text = format_agent_capabilities_for_voice()
    assert "shell" in text or "命令" in text
    assert "dispatch_task" in text
    assert "MCP" in text
    assert "cron" in text


def test_assemble_voice_system_prompt_includes_capabilities():
    base = "你是语音助手。"
    full = assemble_voice_system_prompt(base)
    assert full.startswith("你是语音助手。")
    assert "【当前环境】" in full
    assert "【默认行为】" in full
    assert "【后台 Agent 能做什么】" in full
    assert "dispatch_task" in full
