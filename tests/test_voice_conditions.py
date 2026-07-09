"""Voice 循环控制条件测试。"""
from unittest.mock import MagicMock

from vocamind.common.config import PipelineConfig
from vocamind.voice.conditions import should_continue_voice_loop, should_stream_final_reply
from vocamind.voice.state import VoiceTurnState


def test_should_stream_final_reply_when_no_tools():
    msg = MagicMock()
    msg.tool_calls = None
    assert should_stream_final_reply(msg) is True


def test_should_not_stream_when_has_tool_calls():
    msg = MagicMock()
    msg.tool_calls = [MagicMock()]
    assert should_stream_final_reply(msg) is False


def test_should_continue_until_max_rounds():
    state = VoiceTurnState(tool_round=2)
    config = PipelineConfig(voice_max_tool_rounds=2)
    msg = MagicMock()
    msg.tool_calls = [MagicMock()]
    assert should_continue_voice_loop(state, config, msg) is False


def test_should_continue_when_under_max_rounds():
    state = VoiceTurnState(tool_round=0)
    config = PipelineConfig(voice_max_tool_rounds=2)
    msg = MagicMock()
    msg.tool_calls = [MagicMock()]
    assert should_continue_voice_loop(state, config, msg) is True
