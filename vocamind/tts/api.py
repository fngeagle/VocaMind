"""基于 OpenAI 兼容接口的云端 TTS 实现。"""
from __future__ import annotations

import logging
import os
import time
import unicodedata
from queue import Queue
from threading import Event
from typing import Any, Dict, Iterator, Optional, Union

import numpy as np
import requests

from vocamind.common.config import PipelineConfig
from vocamind.common.audio import float_to_int16, load_mp3, resample
from vocamind.common.timing import log_elapsed
from vocamind.tts.base import TTSHandlerBase
from vocamind.tts.voice_profile import VoiceProfileService

logger = logging.getLogger(__name__)

OUTPUT_SAMPLE_RATE = 16000


def _has_speakable_content(text: str) -> bool:
    """是否含字母/汉字/数字等可朗读字符（跳过纯 emoji、标点）。"""
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith(("L", "N")):
            return True
    return False


class APITTSHandler(TTSHandlerBase):
    """通过 SiliconFlow 等 HTTP API 将 LLM 句子合成为音频。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        should_listen: Event,
        interruption_event: Event,
        config: PipelineConfig,
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out, should_listen, interruption_event)
        self.config = config
        self.api_key = os.getenv(config.tts_api_key_env)
        if not self.api_key:
            raise ValueError(f"环境变量 {config.tts_api_key_env} 未设置")

        self.model_url = config.tts_api_url.rstrip("/") + "/"
        self.tts_url = f"{self.model_url}audio/speech"
        self._voice_profile = VoiceProfileService(config, self.api_key)
        self._session = requests.Session()

    def synthesize(self, text: str, uid: str) -> Optional[np.ndarray]:
        if self._should_stop() or not text.strip():
            return None
        if not _has_speakable_content(text):
            logger.debug("TTS 跳过不可朗读内容: %r", text)
            return None

        ref_start = time.perf_counter()
        ref_uri = self._voice_profile.get_ref_uri()
        log_elapsed("TTS 获取参考音色", ref_start)

        payload = {
            "model": self.config.tts_model,
            "input": text,
            "voice": ref_uri,
            "response_format": "mp3",
            "sample_rate": self.config.tts_sample_rate,
            "stream": False,
            "speed": 1,
            "gain": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        total_start = time.perf_counter()
        api_start = time.perf_counter()
        response = self._session.post(self.tts_url, json=payload, headers=headers, timeout=120)
        log_elapsed("TTS API请求", api_start, text=text[:40], uid=uid)
        if response.status_code != 200:
            logger.error("TTS API 错误: %s %s", response.status_code, response.text[:300])
            return None

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "json" in content_type:
            logger.error("TTS API 返回 JSON 而非音频: %s", response.text[:300])
            return None

        if not response.content:
            logger.debug("TTS API 对 %r 返回空音频，跳过", text[:40])
            return None

        try:
            decode_start = time.perf_counter()
            audio, sr = load_mp3(response.content)
            log_elapsed("TTS 解码MP3", decode_start, bytes=len(response.content))
        except Exception as exc:
            logger.error(
                "TTS 音频解码失败 (text=%r, %d bytes): %s",
                text[:40],
                len(response.content),
                exc,
            )
            return None

        if sr != OUTPUT_SAMPLE_RATE:
            resample_start = time.perf_counter()
            audio = resample(audio, sr, OUTPUT_SAMPLE_RATE)
            log_elapsed("TTS 重采样", resample_start, from_sr=sr, to_sr=OUTPUT_SAMPLE_RATE)
        pcm = float_to_int16(audio)
        log_elapsed("TTS 合成总计", total_start, text=text[:40], uid=uid, pcm_bytes=len(pcm))
        return pcm

    def process(self, inputs: Dict[str, Any]) -> Iterator[Dict[str, Union[str, int, bool, np.ndarray]]]:
        llm_sentence = inputs["answer_text"]
        uid = inputs["uid"]
        end_flag = inputs["end_flag"]
        user_input_count = inputs["user_input_count"]
        question_text = inputs.get("question_text")

        if not llm_sentence and end_flag:
            yield {
                "question_text": None,
                "answer_text": "",
                "answer_audio": "",
                "end_flag": True,
                "user_input_count": user_input_count,
                "uid": uid,
                "proactive": inputs.get("proactive", False),
            }
            self.should_listen.set()
            return

        if self._should_stop():
            self.should_listen.set()
            return

        yield {
            "question_text": question_text,
            "answer_text": llm_sentence,
            "answer_audio": "",
            "end_flag": False,
            "user_input_count": user_input_count,
            "uid": uid,
            "proactive": inputs.get("proactive", False),
        }

        if self._should_stop():
            self.should_listen.set()
            return

        audio = self.synthesize(llm_sentence, uid)
        yield {
            "question_text": None,
            "answer_text": "",
            "answer_audio": audio if audio is not None else "",
            "end_flag": end_flag,
            "user_input_count": user_input_count,
            "uid": uid,
            "proactive": inputs.get("proactive", False),
        }
        self.should_listen.set()
