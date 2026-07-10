"""Agent 运行时构建与启动。"""
from __future__ import annotations

import threading
from typing import Optional

from vocamind.agent.runner import run_agent_daemon
from vocamind.agent.state import AgentRuntime
from vocamind.common.config import PipelineConfig
from vocamind.status import StatusRegistry
from vocamind.tasks.queue import AgentTaskQueue


def build_agent_runtime(
    config: PipelineConfig,
    stop_event,
    task_queue: AgentTaskQueue,
    status_registry: StatusRegistry,
    outbound_queue=None,
) -> AgentRuntime:
    return AgentRuntime(
        stop_event=stop_event,
        task_queue=task_queue,
        status_registry=status_registry,
        outbound_queue=outbound_queue,
    )


def start_agent_runtime(runtime: AgentRuntime, config: PipelineConfig) -> threading.Thread:
    thread = threading.Thread(
        target=run_agent_daemon,
        args=(runtime, config),
        daemon=True,
        name="agent-daemon",
    )
    thread.start()
    # 预留信号：Daemon 线程已 launch，视为空闲；对外查询 idle 仍以 status_registry 为准
    runtime.agent_lock.set()
    return thread
