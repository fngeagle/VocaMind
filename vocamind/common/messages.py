"""各管道阶段队列消息的 TypedDict 契约。"""
from __future__ import annotations

from typing import Optional, TypedDict, Union

import numpy as np


class PromptMessage(TypedDict):
    """Gateway → STT：用户语音段或文本。"""

    data: Union[str, np.ndarray]
    user_input_count: int
    uid: Optional[str]


class TextPrompt(TypedDict):
    """STT → LLM：统一文本提示。"""

    data: str
    user_input_count: int
    uid: Optional[str]
    audio_input: bool


class LLMChunk(TypedDict, total=False):
    """LLM → TTS：按句切分后的助手回复。"""

    question_text: Optional[str]
    answer_text: str
    end_flag: bool
    user_input_count: int
    uid: Optional[str]


class OutboundMessage(TypedDict, total=False):
    """TTS → Gateway → 客户端：出站 JSON。"""

    question_text: Optional[str]
    answer_text: str
    answer_audio: Union[str, bytes, np.ndarray]
    end_flag: bool
    user_input_count: int
    uid: Optional[str]
    placeholder: str
    return_info: str
    type: str
