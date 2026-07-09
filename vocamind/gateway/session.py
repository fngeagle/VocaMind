"""客户端 WebSocket 会话状态。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClientSession:
    """单条 WebSocket 连接上的会话上下文。"""

    uid: Optional[str] = None
    user_input_count: int = 0
    frontend_is_playing: bool = False

    def reset_topic(self) -> None:
        """清空话题计数，保留 uid。"""
        self.user_input_count = 0
        self.frontend_is_playing = False

    def bind_uid(self, uid: str) -> None:
        self.uid = uid
