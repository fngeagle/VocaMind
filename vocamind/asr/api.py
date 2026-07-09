"""基于 OpenAI 兼容接口的云端 ASR 实现（如 SiliconFlow）。"""
from __future__ import annotations

import io
import logging
import os
import time
from queue import Queue
from threading import Event
from typing import Optional

import numpy as np
import requests

from vocamind.asr.base import STTHandlerBase
from vocamind.common.config import PipelineConfig
from vocamind.common.audio import encode_wav
from vocamind.common.timing import log_elapsed

logger = logging.getLogger(__name__)


class APISTTHandler(STTHandlerBase):
    """通过 HTTP API 将音频转为文本。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        config: PipelineConfig,
        interruption_event: Optional[Event] = None,
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out)
        self.config = config
        self.interruption_event = interruption_event
        self.api_key = os.getenv(config.asr_api_key_env)
        if not self.api_key:
            raise ValueError(f"环境变量 {config.asr_api_key_env} 未设置")

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if self.interruption_event and self.interruption_event.is_set():
            logger.info("ASR 因打断而跳过")
            return ""

        total_start = time.perf_counter()
        encode_start = time.perf_counter()
        wav_bytes = encode_wav(audio, sample_rate)
        log_elapsed("ASR 编码WAV", encode_start, samples=len(audio))

        files = {
            "file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            "model": (None, self.config.asr_model),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        api_start = time.perf_counter()
        response = requests.post(self.config.asr_api_url, files=files, headers=headers, timeout=60)
        response.raise_for_status()
        log_elapsed("ASR API请求", api_start)
        text = response.json().get("text", "")
        log_elapsed("ASR 识别总计", total_start, text=text)
        logger.info("ASR 识别结果: %s", text)
        return text
