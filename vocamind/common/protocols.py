"""管道节点协议定义。"""
from __future__ import annotations

from threading import Event
from typing import Protocol, runtime_checkable


@runtime_checkable
class PipelineNode(Protocol):
    """管道中可独立线程运行的节点（Handler 或 WebSocket 网关）。"""

    stop_event: Event

    def start(self) -> None:
        """在工作线程中启动节点主循环。"""
        ...
