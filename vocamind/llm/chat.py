"""LLM 对话历史滑动窗口。"""
from __future__ import annotations

from typing import Dict, List


class Chat:
    """滑动窗口对话历史，供 LLM 构造 messages。"""

    def __init__(self, size: int, user_role: str = "user", assistant_role: str = "assistant") -> None:
        self.size = size
        self.user_role = user_role
        self.assistant_role = assistant_role
        self.init_chat_message: Dict[str, str] | None = None
        self.buffer: List[Dict[str, str]] = []

    def init_chat(self, message: Dict[str, str]) -> None:
        self.init_chat_message = message

    def append(self, item: Dict[str, str]) -> None:
        self.buffer.append(item)
        if len(self.buffer) == 2 * (self.size + 1):
            self.buffer.pop(0)
            self.buffer.pop(0)

    def to_list(self) -> List[Dict[str, str]]:
        if self.init_chat_message:
            return [self.init_chat_message] + self.buffer
        return list(self.buffer)

    def clear(self) -> None:
        self.buffer = []
