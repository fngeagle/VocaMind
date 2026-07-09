"""对话上下文存档测试。"""
import json
from pathlib import Path

from vocamind.common.conversation_log import (
    build_agent_record,
    build_voice_record,
    get_conversations_dir,
    save_agent_task,
    save_voice_turn,
    serialize_messages,
)
from vocamind.voice.state import VoiceTurnState


def test_save_voice_turn_utf8(tmp_path: Path):
    get_conversations_dir(tmp_path / ".conversations")
    state = VoiceTurnState(
        prompt="写一份世界杯报告",
        user_input_count=2,
        uid="user-abc",
        assistant_raw="好，已经交给后台写了。",
        assistant_spoken="好，已经交给后台写了。",
        started_at="2026-07-09T14:00:00+08:00",
    )
    state.messages = [
        {"role": "user", "content": "写一份世界杯报告"},
        {"role": "assistant", "content": "好，已经交给后台写了。"},
    ]
    path = save_voice_turn(build_voice_record(state=state, system_prompt="你是语音助手"))
    raw = path.read_text(encoding="utf-8")
    assert "世界杯报告" in raw
    assert "\\u" not in raw
    data = json.loads(raw)
    assert data["kind"] == "voice_turn"
    assert data["outputs"]["assistant_stream_merged"] == "好，已经交给后台写了。"


def test_save_agent_task_with_tool_output(tmp_path: Path):
    get_conversations_dir(tmp_path / ".conversations")
    long_output = "x" * 9000
    record = build_agent_record(
        task_id="task_001",
        subject="测试",
        description="做某事",
        source="voice",
        uid="u1",
        user_input_count=1,
        messages=[
            {"role": "user", "content": "Task: 测试"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "bash", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": long_output},
            {"role": "assistant", "content": "完成了"},
        ],
        summary="完成了",
        system_prompt="你是 Agent",
        started_at="2026-07-09T14:00:00+08:00",
        round_count=2,
        failed=False,
    )
    path = save_agent_task(record)
    data = json.loads(path.read_text(encoding="utf-8"))
    tool_msg = [m for m in data["llm_messages"] if m["role"] == "tool"][0]
    assert tool_msg["content_length"] == 9000
    assert len(tool_msg["content"]) < 9000


def test_serialize_messages_keeps_short_tool_content():
    messages = [{"role": "tool", "tool_call_id": "t1", "content": "ok"}]
    assert serialize_messages(messages)[0]["content"] == "ok"
