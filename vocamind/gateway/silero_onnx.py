"""Silero VAD ONNX 推理：纯 NumPy + ONNX Runtime，无需 PyTorch。"""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort

logger = logging.getLogger(__name__)

SILERO_VAD_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def resolve_model_path(model_path: Optional[str] = None) -> Path:
    """解析模型路径，不存在时自动下载。"""
    if model_path:
        path = Path(model_path)
    else:
        path = DEFAULT_MODEL_DIR / "silero_vad.onnx"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("正在下载 Silero VAD ONNX 模型: %s", SILERO_VAD_URL)
    urllib.request.urlretrieve(SILERO_VAD_URL, path)
    logger.info("模型已保存至 %s", path)
    return path


class SileroOnnxVAD:
    """Silero VAD ONNX 封装，接口与原版模型兼容。"""

    CHUNK_SAMPLES = {8000: 256, 16000: 512}
    CONTEXT_SIZE = {8000: 32, 16000: 64}

    def __init__(self, model_path: Optional[str] = None, use_gpu: bool = False) -> None:
        path = str(resolve_model_path(model_path))
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        providers = ort.get_available_providers()
        if use_gpu and "CUDAExecutionProvider" in providers:
            session_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            session_providers = ["CPUExecutionProvider"]

        self.session = ort.InferenceSession(path, sess_options=opts, providers=session_providers)
        self.sample_rates = [8000, 16000]
        self.reset_states()

    def reset_states(self, batch_size: int = 1) -> None:
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context: Optional[np.ndarray] = None
        self._last_sr = 0
        self._last_batch_size = 0

    def _validate(self, x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        if x.ndim > 2:
            raise ValueError(f"音频维度过多: {x.ndim}")
        if sr != 16000 and sr % 16000 == 0:
            step = sr // 16000
            x = x[:, ::step]
            sr = 16000
        if sr not in self.sample_rates:
            raise ValueError(f"不支持的采样率: {sr}")
        return x, sr

    def __call__(self, x: np.ndarray, sr: int) -> float:
        x, sr = self._validate(x, sr)
        num_samples = self.CHUNK_SAMPLES[sr]
        if x.shape[-1] != num_samples:
            raise ValueError(f"每帧需 {num_samples} 个采样点，实际 {x.shape[-1]}")

        batch_size = x.shape[0]
        context_size = self.CONTEXT_SIZE[sr]

        if not self._last_batch_size or self._last_sr != sr or self._last_batch_size != batch_size:
            self.reset_states(batch_size)
        if self._context is None:
            self._context = np.zeros((batch_size, context_size), dtype=np.float32)

        x = np.concatenate([self._context, x], axis=1)
        ort_inputs = {
            "input": x.astype(np.float32),
            "state": self._state,
            "sr": np.array(sr, dtype=np.int64),
        }
        out, state = self.session.run(None, ort_inputs)
        self._state = state
        self._context = x[:, -context_size:]
        self._last_sr = sr
        self._last_batch_size = batch_size
        return float(out[0, 0])


class VADIterator:
    """流式 VAD 迭代器：累积语音片段直至检测到句末静音。"""

    def __init__(
        self,
        model: SileroOnnxVAD,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        min_silence_duration_ms: int = 100,
        speech_pad_ms: int = 30,
        max_speech_ms: int = 60000,
    ) -> None:
        self.model = model
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.buffer: list[np.ndarray] = []
        self.min_silence_samples = sampling_rate * min_silence_duration_ms / 1000
        self.speech_pad_samples = sampling_rate * speech_pad_ms / 1000
        self.max_speech_samples = sampling_rate * max_speech_ms / 1000
        self.reset_states()

    def reset_states(self) -> None:
        self.model.reset_states()
        self.triggered = False
        self.temp_end = 0
        self.current_sample = 0

    def __call__(self, x: np.ndarray) -> Optional[list[np.ndarray]]:
        x = np.asarray(x, dtype=np.float32)
        window_size = x.shape[0]
        self.current_sample += window_size
        speech_prob = self.model(x.reshape(1, -1), self.sampling_rate)

        if speech_prob >= self.threshold and self.temp_end:
            self.temp_end = 0

        if speech_prob >= self.threshold and not self.triggered:
            self.triggered = True
            return None

        if (speech_prob < self.threshold - 0.15) and self.triggered:
            if not self.temp_end:
                self.temp_end = self.current_sample
            if self.current_sample - self.temp_end < self.min_silence_samples:
                return None
            self.temp_end = 0
            self.triggered = False
            spoken = self.buffer
            self.buffer = []
            return spoken

        if len(self.buffer) * window_size >= self.max_speech_samples:
            self.temp_end = 0
            self.triggered = False
            spoken = self.buffer
            self.buffer = []
            return spoken

        if self.triggered:
            self.buffer.append(x)
        return None
