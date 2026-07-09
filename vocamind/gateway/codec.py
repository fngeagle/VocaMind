"""WebSocket 出站消息编解码。"""
from __future__ import annotations

import base64
import json
from typing import Any, Union

import numpy as np


def normalize_outbound_audio(data: dict) -> None:
    """将 answer_audio 统一转为 bytes，供 JSON 序列化。"""
    audio = data.get("answer_audio")
    if isinstance(audio, np.ndarray):
        data["answer_audio"] = audio.tobytes()
    elif isinstance(audio, (bytes, bytearray)):
        data["answer_audio"] = bytes(audio)


class OutboundJsonEncoder(json.JSONEncoder):
    """将 bytes 序列化为 base64 字符串。"""

    def default(self, obj: Any) -> Union[str, Any]:
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("utf-8")
        return super().default(obj)
