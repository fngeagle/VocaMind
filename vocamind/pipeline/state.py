"""管道编排状态：跨节点共享的事件、队列与会话生命周期。"""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from threading import Event
from typing import Any, Optional

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
    """
    封装管道中跨节点共享的状态与队列。

    Gateway / Voice LLM / TTS / Agent 四个线程通过本对象传递消息、
    协调打断与会话生命周期，由 build_pipeline() 创建并注入各节点。
    """

    # --- 生命周期与协调 ---
    stop_event: Event  # 全局停止；置位后所有 Handler 退出主循环
    should_listen: Event  # 是否允许 Gateway 接收用户输入；TTS 播报期间通常清除
    interruption_event: Event  # 用户打断信号；置位后 LLM/TTS 停止当前轮次输出
    assistant_turn_active: Event  # 助手正在回复；用于判断是否应触发打断
    session: SessionLifecycle  # 连接断开/新话题时的 flush 信号

    # --- 主数据流队列（Gateway → Voice → TTS → Gateway）---
    text_prompt_queue: Queue  # 用户文本 / 任务通知 → Voice LLM
    lm_response_queue: Queue  # LLM 流式回复 → TTS
    outbound_queue: Queue  # TTS 音频或文本 → 推送给客户端

    # uid → 任务完成时待随 Voice 结束一并下发的文档附件
    pending_attachments: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    # --- Agent 后台 ---
    task_queue: AgentTaskQueue = field(default_factory=AgentTaskQueue)  # Voice 派发的后台任务
    status_registry: StatusRegistry = field(default_factory=StatusRegistry)  # 任务/工具执行状态
    agent_runtime: Optional[AgentRuntime] = None  # Agent Daemon 运行时；build_pipeline 中初始化

    @property
    def cur_conn_end_event(self) -> Event:
        """兼容 Handler 基类对 cur_conn_end_event 的引用，实际指向 session.flush。"""
        return self.session.cur_conn_end_event

    @classmethod
    def create(cls) -> PipelineContext:
        """创建一份空的管道上下文，所有 Event 初始为未置位。"""
        return cls(
            stop_event=Event(),
            should_listen=Event(),
            interruption_event=Event(),
            assistant_turn_active=Event(),
            session=SessionLifecycle(),
            text_prompt_queue=Queue(),
            lm_response_queue=Queue(),
            outbound_queue=Queue(),
        )
