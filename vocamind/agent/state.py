"""Agent Loop 编排状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    round_count: int = 0
    compacted_now: bool = False
    completed_by_tool: bool = False
    failed: bool = False


@dataclass
class AgentRuntime:
    """跨线程 Agent 运行时资源。"""

    stop_event: Event
    task_queue: AgentTaskQueue
    status_registry: StatusRegistry
    agent_lock: Event = field(default_factory=Event)

    def __post_init__(self) -> None:
        self.agent_lock.set()
