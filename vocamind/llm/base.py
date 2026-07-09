"""LLM Handler 抽象。"""
from __future__ import annotations

import threading
from queue import Queue
from threading import Event
from typing import Dict, List

from vocamind.common.handler import BaseHandler
from vocamind.llm.chat import Chat


class LLMHandlerBase(BaseHandler):
    """大模型节点基类：流式生成并按句 yield。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        interruption_event: Event,
        chat_size: int = 5,
        system_prompt: str = "",
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out)
        self.interruption_event = interruption_event
        self._inference_lock = threading.Lock()
        self.chat = Chat(chat_size)
        if system_prompt:
            self.chat.init_chat({"role": "system", "content": system_prompt})
        self.user_role = "user"
        self.assistant_role = "assistant"

    def clear_current_state(self) -> None:
        super().clear_current_state()
        self.chat.clear()

    def _append_user(self, prompt: str) -> List[Dict[str, str]]:
        self.chat.append({"role": self.user_role, "content": prompt})
        return self.chat.to_list()

    def _append_assistant(self, text: str) -> None:
        if not self.cur_conn_end_event.is_set():
            self.chat.append({"role": self.assistant_role, "content": text})
