"""全局只读状态注册表：Voice LLM 可查询所有子系统状态。"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from vocamind.tasks import list_tasks


@dataclass
class AgentRuntimeStatus:
    """Agent Loop 运行态（由 agent 编排层写入）。"""

    idle: bool = True
    current_task_id: Optional[str] = None
    round_count: int = 0


@dataclass
class PipelineRuntimeStatus:
    """管道运行态（由 pipeline 注入，只读）。"""

    should_listen: bool = False
    connected: bool = False


@dataclass
class StatusSnapshot:
    tasks: list[dict[str, Any]] = field(default_factory=list)
    agent: AgentRuntimeStatus = field(default_factory=AgentRuntimeStatus)
    todos: list[dict[str, Any]] = field(default_factory=list)
    background: dict[str, Any] = field(default_factory=dict)
    crons: list[dict[str, Any]] = field(default_factory=list)
    teammates: list[str] = field(default_factory=list)
    mcp: list[str] = field(default_factory=list)
    pipeline: PipelineRuntimeStatus = field(default_factory=PipelineRuntimeStatus)
    queue_pending: int = 0


class StatusRegistry:
    """聚合各功能层状态，提供统一快照接口。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agent = AgentRuntimeStatus()
        self._pipeline = PipelineRuntimeStatus()
        self._todos: list[dict[str, Any]] = []
        self._background_tasks: dict[str, dict[str, Any]] = {}
        self._background_results: dict[str, str] = {}
        self._crons: list[dict[str, Any]] = []
        self._teammates: list[str] = []
        self._mcp: list[str] = []
        self._queue_pending: int = 0

    def update_agent(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._agent, key):
                    setattr(self._agent, key, value)

    def update_pipeline(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._pipeline, key):
                    setattr(self._pipeline, key, value)

    def set_todos(self, todos: list[dict[str, Any]]) -> None:
        with self._lock:
            self._todos = list(todos)

    def set_background(self, tasks: dict[str, dict], results: dict[str, str]) -> None:
        with self._lock:
            self._background_tasks = dict(tasks)
            self._background_results = dict(results)

    def set_crons(self, crons: list[dict[str, Any]]) -> None:
        with self._lock:
            self._crons = list(crons)

    def set_teammates(self, names: list[str]) -> None:
        with self._lock:
            self._teammates = list(names)

    def set_mcp(self, names: list[str]) -> None:
        with self._lock:
            self._mcp = list(names)

    def set_queue_pending(self, count: int) -> None:
        with self._lock:
            self._queue_pending = count

    def snapshot(self) -> StatusSnapshot:
        with self._lock:
            tasks = [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "status": t.status,
                    "owner": t.owner,
                    "blockedBy": t.blockedBy,
                }
                for t in list_tasks()
            ]
            return StatusSnapshot(
                tasks=tasks,
                agent=AgentRuntimeStatus(
                    idle=self._agent.idle,
                    current_task_id=self._agent.current_task_id,
                    round_count=self._agent.round_count,
                ),
                todos=list(self._todos),
                background={
                    "tasks": dict(self._background_tasks),
                    "recent_results": dict(self._background_results),
                },
                crons=list(self._crons),
                teammates=list(self._teammates),
                mcp=list(self._mcp),
                pipeline=PipelineRuntimeStatus(
                    should_listen=self._pipeline.should_listen,
                    connected=self._pipeline.connected,
                ),
                queue_pending=self._queue_pending,
            )

    def snapshot_json(self, indent: int = 2) -> str:
        snap = self.snapshot()
        data = asdict(snap)
        return json.dumps(data, indent=indent, ensure_ascii=False)


def query_all_status(registry: StatusRegistry) -> str:
    return registry.snapshot_json()
