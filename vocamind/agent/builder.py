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
) -> AgentRuntime:
    return AgentRuntime(
        stop_event=stop_event,
        task_queue=task_queue,
        status_registry=status_registry,
    )


def start_agent_runtime(runtime: AgentRuntime, config: PipelineConfig) -> threading.Thread:
    thread = threading.Thread(
        target=run_agent_daemon,
        args=(runtime, config),
        daemon=True,
        name="agent-daemon",
    )
    thread.start()
    runtime.agent_lock.set()
    return thread
