"""管道 Handler 基类与线程管理。"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from queue import Empty, Queue
from threading import Event
from typing import Any, Dict, Iterator, List

from vocamind.common.handler_conditions import handle_queue_idle, should_continue_handler
from vocamind.common.protocols import PipelineNode

logger = logging.getLogger(__name__)


class ThreadManager:
    """管理管道中各 PipelineNode 所在的工作线程。"""

    def __init__(self, handlers: List[PipelineNode]) -> None:
        self.handlers = handlers
        self.threads: List[threading.Thread] = []

    def start(self) -> None:
        for handler in self.handlers:
            if not isinstance(handler, PipelineNode):
                raise TypeError(f"节点未实现 PipelineNode 协议: {type(handler)!r}")
            thread = threading.Thread(target=handler.start, daemon=True)
            self.threads.append(thread)
            thread.start()

    def stop(self) -> None:
        for handler in self.handlers:
            handler.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=5)

    def join(self) -> None:
        for thread in self.threads:
            thread.join()


class BaseHandler(ABC):
    """管道节点基类：从输入队列取数据，处理后写入输出队列。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
    ) -> None:
        self.stop_event = stop_event
        self.cur_conn_end_event = cur_conn_end_event
        self.queue_in = queue_in
        self.queue_out = queue_out

    @abstractmethod
    def process(self, data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        raise NotImplementedError

    def start(self) -> None:
        """PipelineNode 统一入口。"""
        self.run()

    def run(self) -> None:
        while should_continue_handler(self.stop_event):
            try:
                item = self.queue_in.get(timeout=0.2)
            except Empty:
                handle_queue_idle(self)
                continue
            try:
                for output in self.process(item):
                    self.queue_out.put(output)
            except Exception:
                logger.exception("%s 处理失败", self.__class__.__name__)
        self.cleanup()

    def cleanup(self) -> None:
        pass

    def clear_current_state(self) -> None:
        while not self.queue_in.empty():
            try:
                self.queue_in.get_nowait()
            except Empty:
                break
        while not self.queue_out.empty():
            try:
                self.queue_out.get_nowait()
            except Empty:
                break
