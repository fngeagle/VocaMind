"""ASR Handler 抽象：统一语音/文本输入的输出格式。"""
from __future__ import annotations

from abc import abstractmethod
from queue import Queue
from threading import Event
from typing import Any, Dict, Iterator, Union

import numpy as np

from vocamind.common.handler import BaseHandler


class STTHandlerBase(BaseHandler):
    """
    语音识别节点基类。
    输入 data 为 str（文本直传）或 np.ndarray（音频），
    输出统一为 {"data": str, "user_input_count", "uid", "audio_input": bool}。
    """

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        raise NotImplementedError

    def process(self, inputs: Dict[str, Any]) -> Iterator[Dict[str, Union[str, int, bool]]]:
        spoken_prompt = inputs["data"]
        user_input_count = inputs["user_input_count"]
        uid = inputs["uid"]

        if isinstance(spoken_prompt, str):
            yield {
                "data": spoken_prompt,
                "user_input_count": user_input_count,
                "uid": uid,
                "audio_input": False,
            }
            return

        sample_rate = inputs.get("sample_rate", 16000)
        text = self.transcribe(spoken_prompt, sample_rate)
        yield {
            "data": text,
            "user_input_count": user_input_count,
            "uid": uid,
            "audio_input": True,
        }
