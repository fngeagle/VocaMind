"""轻量音频工具：读写 WAV、重采样、格式转换（无 PyTorch 依赖）。"""
from __future__ import annotations

import io
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def encode_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    """将 float32 单声道音频编码为 WAV 字节流。"""
    buf = io.BytesIO()
    samples = np.asarray(audio, dtype=np.float32).squeeze()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()


def load_wav(data: bytes) -> tuple[np.ndarray, int]:
    """从 WAV 字节流解码为 float32 单声道音频。"""
    buf = io.BytesIO(data)
    audio, sr = sf.read(buf, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), int(sr)


def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """重采样到目标采样率。"""
    if orig_sr == target_sr:
        return np.asarray(audio, dtype=np.float32)
    factor = gcd(orig_sr, target_sr)
    return resample_poly(audio, target_sr // factor, orig_sr // factor).astype(np.float32)


def load_mp3(data: bytes) -> tuple[np.ndarray, int]:
    """从 MP3 字节流解码为 float32 单声道音频。"""
    if not data:
        raise ValueError("MP3 数据为空")
    if data.lstrip()[:1] == b"{":
        raise ValueError(f"响应似为 JSON 而非音频: {data[:200]!r}")

    import miniaudio

    try:
        decoded = miniaudio.decode(data)
    except miniaudio.DecodeError as exc:
        raise ValueError(f"MP3 解码失败 ({len(data)} bytes): {exc}") from exc

    samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
    if decoded.nchannels > 1:
        samples = samples.reshape(-1, decoded.nchannels).mean(axis=1)
    return samples, decoded.sample_rate


def float_to_int16(audio: np.ndarray) -> np.ndarray:
    """float32 [-1, 1] 转 int16 PCM。"""
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
