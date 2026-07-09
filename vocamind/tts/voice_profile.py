"""TTS 参考音色懒加载与缓存。"""
from __future__ import annotations

import glob
import json
import logging
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from vocamind.common.config import PipelineConfig
from vocamind.common.timing import log_elapsed

logger = logging.getLogger(__name__)


def load_ref_entries(ref_dir: str) -> List[Tuple[str, str]]:
    """收集 (wav 绝对路径, prompt 文本) 列表。"""
    entries: List[Tuple[str, str]] = []
    json_path = os.path.join(ref_dir, "ref.json")
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            for item in json.load(f):
                name = os.path.basename(item.get("ref_wav_path", ""))
                text = (item.get("prompt_text") or "").strip()
                if not name or not text:
                    continue
                for candidate in (
                    os.path.join(ref_dir, "ref_wav", name),
                    os.path.join(ref_dir, name),
                ):
                    if os.path.exists(candidate):
                        entries.append((candidate, text))
                        break

    if entries:
        return entries

    for wav_file in glob.glob(os.path.join(ref_dir, "*.wav")):
        txt_file = os.path.splitext(wav_file)[0] + ".txt"
        text = ""
        if os.path.exists(txt_file):
            with open(txt_file, encoding="utf-8") as tf:
                text = tf.read().strip()
        if text:
            entries.append((wav_file, text))
    return entries


class VoiceProfileService:
    """首次合成时解析参考音色 URI，避免阻塞管道启动。"""

    def __init__(self, config: PipelineConfig, api_key: str) -> None:
        self.config = config
        self.api_key = api_key
        self._uri: Optional[str] = None
        self._lock = threading.Lock()
        self.model_url = config.tts_api_url.rstrip("/") + "/"
        self.upload_url = urljoin(self.model_url, "uploads/audio/voice")
        self.list_ref_url = urljoin(self.model_url, "audio/voice/list")

    def get_ref_uri(self) -> str:
        with self._lock:
            if self._uri is not None:
                return self._uri
            self._uri = self._resolve_reference_voice()
            return self._uri

    def _resolve_reference_voice(self) -> str:
        total_start = time.perf_counter()
        uploaded_uris: List[str] = []
        for wav_path, text in load_ref_entries(self.config.ref_dir):
            uri = self._upload_reference_audio(wav_path, text)
            if uri:
                uploaded_uris.append(uri)

        if uploaded_uris:
            uri = random.choice(uploaded_uris)
            log_elapsed("TTS 参考音色解析", total_start, uri=uri, source="upload")
            logger.info("已选择 TTS 参考音色: %s", uri)
            return uri

        usable = self._list_usable_voices()
        if usable:
            uri = random.choice(usable)["uri"]
            log_elapsed("TTS 参考音色解析", total_start, uri=uri, source="list")
            logger.info("使用已有参考音色: %s", uri)
            return uri

        raise RuntimeError(
            f"参考音频目录 {self.config.ref_dir} 中未找到可用音色。"
            "请确保 ref.json + ref_wav/*.wav 存在，且 prompt_text 非空。"
        )

    def _upload_reference_audio(self, wav_path: str, text: str) -> Optional[str]:
        upload_start = time.perf_counter()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        basename = os.path.basename(wav_path)
        voice_name = f"vocamind_{os.path.splitext(basename)[0]}"
        with open(wav_path, "rb") as audio_f:
            response = requests.post(
                self.upload_url,
                headers=headers,
                files={"file": audio_f},
                data={
                    "model": self.config.tts_model,
                    "customName": voice_name,
                    "text": text,
                },
                timeout=60,
            )
        log_elapsed("TTS 上传参考音色", upload_start, file=basename)
        if response.status_code != 200:
            logger.warning(
                "上传参考音频 %s 失败: %s %s",
                basename,
                response.status_code,
                response.text[:200],
            )
            return None
        uri = response.json().get("uri")
        if uri:
            logger.info("已上传参考音色 %s -> %s", basename, uri)
        return uri

    def _list_usable_voices(self) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = requests.get(self.list_ref_url, headers=headers, timeout=30)
        response.raise_for_status()
        voices = response.json().get("result", [])
        return [
            v
            for v in voices
            if v.get("model") == self.config.tts_model and (v.get("text") or "").strip()
        ]
