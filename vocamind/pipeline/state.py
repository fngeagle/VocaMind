"""管道编排状态：跨节点共享的事件、队列与会话生命周期。"""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from threading import Event
from typing import Optional

from vocamind.agent.state import AgentRuntime
from vocamind.status import StatusRegistry
from vocamind.tasks.queue import AgentTaskQueue


class SessionLifecycle:
    """
    管理会话级 flush 信号。

    flush_requested 置位时，各 Handler 在队列空闲轮询中清空积压消息；
    新连接建立时清除，允许新一轮对话。
    """

    def __init__(self) -> None:
        self._flush_requested = Event()

    @property
    def flush_requested(self) -> Event:
        return self._flush_requested

    @property
    def cur_conn_end_event(self) -> Event:
        """兼容既有 Handler 对 cur_conn_end_event 的引用。"""
        return self._flush_requested

    def signal_connect(self) -> None:
        """新 WebSocket 连接建立。"""
        self._flush_requested.clear()

    def signal_disconnect(self) -> None:
        """连接断开，请求清空管道积压。"""
        self._flush_requested.set()

    def signal_new_topic(self) -> None:
        """用户请求开启新话题。"""
        self._flush_requested.set()


@dataclass
class PipelineContext:
    """封装管道中跨节点共享的状态与队列。"""

    stop_event: Event
    should_listen: Event
    interruption_event: Event
    assistant_turn_active: Event
    session: SessionLifecycle
    spoken_prompt_queue: Queue
    text_prompt_queue: Queue
    lm_response_queue: Queue
    outbound_queue: Queue
    task_queue: AgentTaskQueue = field(default_factory=AgentTaskQueue)
    status_registry: StatusRegistry = field(default_factory=StatusRegistry)
    agent_runtime: Optional[AgentRuntime] = None

    @property
    def cur_conn_end_event(self) -> Event:
        return self.session.cur_conn_end_event

    @classmethod
    def create(cls) -> PipelineContext:
        return cls(
            stop_event=Event(),
            should_listen=Event(),
            interruption_event=Event(),
            assistant_turn_active=Event(),
            session=SessionLifecycle(),
            spoken_prompt_queue=Queue(),
            text_prompt_queue=Queue(),
            lm_response_queue=Queue(),
            outbound_queue=Queue(),
        )
