"""Voice LLM 循环控制条件（不含意图关键词判断，意图由提示词约束）。"""
from __future__ import annotations

from vocamind.common.config import PipelineConfig
from vocamind.llm.tool_client import has_tool_calls
from vocamind.voice.state import VoiceTurnState


def should_continue_voice_loop(state: VoiceTurnState, config: PipelineConfig, assistant_message: object) -> bool:
    if state.tool_round >= config.voice_max_tool_rounds:
        return False
    return has_tool_calls(assistant_message)


def should_stream_final_reply(assistant_message: object) -> bool:
    return not has_tool_calls(assistant_message)
