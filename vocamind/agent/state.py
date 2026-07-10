"""Agent Loop 编排状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from threading import Event
from typing import Any, Optional

from vocamind.llm.tool_client import RecoveryState
from vocamind.status import StatusRegistry
from vocamind.tasks.queue import AgentTaskQueue


@dataclass
class AgentContext:
    """单次 agent_loop 运行上下文。"""

    messages: list[dict[str, Any]] = field(default_factory=list)
    recovery: RecoveryState = field(default_factory=RecoveryState)
    max_tokens: int = 4096
    current_task_id: Optional[str] = None
    uid: Optional[str] = None
    user_input_count: int = 0
    round_count: int = 0
    web_search_count: int = 0
    compacted_now: bool = False
    completed_by_tool: bool = False
    failed: bool = False


@dataclass
class AgentRuntime:
    """跨线程 Agent 运行时资源。

    Agent 忙闲的对外查询请用 status_registry.agent.idle（行为真相源）。
    agent_lock 为预留信号，当前无读者；set=空闲，clear=忙碌。
    """
    stop_event: Event
    task_queue: AgentTaskQueue
    status_registry: StatusRegistry
    outbound_queue: Optional[Queue] = None
    agent_lock: Event = field(default_factory=Event)  # 预留；非互斥锁，勿用于同步
