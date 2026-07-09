"""TTS Handler 抽象。"""
from __future__ import annotations

from abc import abstractmethod
from queue import Queue
from threading import Event
from typing import Any, Dict, Iterator, Optional, Union

import numpy as np

from vocamind.common.handler import BaseHandler


class TTSHandlerBase(BaseHandler):
    """语音合成节点基类。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        should_listen: Event,
        interruption_event: Event,
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out)
        self.should_listen = should_listen
        self.interruption_event = interruption_event

    @abstractmethod
    def synthesize(self, text: str, uid: str) -> Optional[np.ndarray]:
        """将单句文本合成为 int16 PCM 音频（16kHz mono）。"""
        raise NotImplementedError

    def _should_stop(self) -> bool:
        return self.interruption_event.is_set() or self.cur_conn_end_event.is_set()
