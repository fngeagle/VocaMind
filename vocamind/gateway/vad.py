"""Silero VAD 语音切段（无 WebSocket 依赖）。"""
from __future__ import annotations

import logging
import time
from threading import Event
from typing import Optional

import numpy as np

from vocamind.common.timing import log_elapsed
from vocamind.gateway.silero_onnx import SileroOnnxVAD, VADIterator

logger = logging.getLogger(__name__)

SILERO_FRAME_SAMPLES = 512


class VADProcessor:
    """对 float32 PCM 块运行 VAD，输出完整语音段。"""

    def __init__(
        self,
        should_listen: Event,
        interruption_event: Event,
        *,
        chunk_size: int = SILERO_FRAME_SAMPLES * 4,
        enable_interruption: bool = True,
        thresh: float = 0.3,
        sample_rate: int = 16000,
        min_silence_ms: int = 1200,
        min_speech_ms: int = 400,
        max_speech_ms: float = float("inf"),
        speech_pad_ms: int = 30,
        vad_model_path: Optional[str] = None,
        vad_use_gpu: bool = False,
    ) -> None:
        self.should_listen = should_listen
        self.interruption_event = interruption_event
        self.chunk_size = chunk_size
        self.enable_interruption = enable_interruption
        self.sample_rate = sample_rate
        self.min_speech_ms = min_speech_ms
        self.max_speech_ms = max_speech_ms
        self.last_speech_started = False

        model = SileroOnnxVAD(model_path=vad_model_path, use_gpu=vad_use_gpu)
        self._iterator = VADIterator(
            model,
            threshold=thresh,
            sampling_rate=sample_rate,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )

    def _maybe_interrupt(self, *, frontend_is_playing: bool, assistant_turn_active: bool) -> None:
        """在检测到用户发声或发送消息时触发打断。"""
        if not self.enable_interruption:
            return
        if frontend_is_playing or assistant_turn_active:
            self.interruption_event.set()
            logger.info("触发用户打断")

    def process_chunk(
        self,
        audio_chunk: bytes,
        frontend_is_playing: bool,
        assistant_turn_active: bool = False,
    ) -> Optional[np.ndarray]:
        """处理一块 PCM，检测到完整语句时返回 float32 数组。"""
        chunk_start = time.perf_counter()
        audio_f32 = np.frombuffer(audio_chunk, dtype=np.float32)
        was_triggered = self._iterator.triggered
        vad_output = self._iterator(audio_f32)
        self.last_speech_started = self._iterator.triggered and not was_triggered

        if self.last_speech_started:
            self._maybe_interrupt(
                frontend_is_playing=frontend_is_playing,
                assistant_turn_active=assistant_turn_active,
            )

        if vad_output is None or len(vad_output) == 0:
            return None

        array = np.concatenate(vad_output).astype(np.float32)
        duration_ms = len(array) / self.sample_rate * 1000
        log_elapsed("VAD 切段", chunk_start, speech_ms=f"{duration_ms:.0f}")
        logger.info("VAD 检测到语音结束，时长 %.0f ms", duration_ms)
        if duration_ms < self.min_speech_ms or duration_ms > self.max_speech_ms:
            logger.info("语音时长 %.2fs 不在有效范围，跳过", len(array) / self.sample_rate)
            return None

        self._maybe_interrupt(
            frontend_is_playing=frontend_is_playing,
            assistant_turn_active=assistant_turn_active,
        )

        if not self.enable_interruption:
            self.should_listen.clear()
            logger.info("已暂停监听，等待 TTS 完成")

        return array

    def maybe_interrupt_user_input(
        self,
        *,
        frontend_is_playing: bool,
        assistant_turn_active: bool,
    ) -> None:
        """用户发送文本时，若助手正在回复则触发打断。"""
        self._maybe_interrupt(
            frontend_is_playing=frontend_is_playing,
            assistant_turn_active=assistant_turn_active,
        )
