"""网关所需的会话信号协议（不依赖编排层类型）。"""
from __future__ import annotations

from typing import Protocol


class SessionSignals(Protocol):
    """连接/断连/新话题时由网关触发的会话信号。"""

    def signal_connect(self) -> None: ...

    def signal_disconnect(self) -> None: ...

    def signal_new_topic(self) -> None: ...
