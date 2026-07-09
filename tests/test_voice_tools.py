"""Voice 工具测试。"""
from pathlib import Path
from threading import Event

from vocamind.agent.state import AgentRuntime
from vocamind.status import StatusRegistry
from vocamind.tasks.queue import AgentTaskQueue
from vocamind.tasks.store import get_task_store
from vocamind.voice.tools import build_voice_handlers


def test_dispatch_task_enqueues(tmp_path: Path):
    get_task_store(tmp_path / ".tasks")
    stop = Event()
    queue = AgentTaskQueue()
    registry = StatusRegistry()
    runtime = AgentRuntime(stop_event=stop, task_queue=queue, status_registry=registry)
    handlers = build_voice_handlers(runtime, registry, user_input_count=1, uid="u1")

    result = handlers["dispatch_task"](subject="测试任务", description="做某事")
    assert "Dispatched" in result
    assert queue.pending_count == 1
    msg = queue.try_dequeue()
    assert msg is not None
    assert msg.subject == "测试任务"
    assert msg.source == "voice"


def test_query_status_returns_json():
    stop = Event()
    queue = AgentTaskQueue()
    registry = StatusRegistry()
    runtime = AgentRuntime(stop_event=stop, task_queue=queue, status_registry=registry)
    handlers = build_voice_handlers(runtime, registry)
    text = handlers["query_status"]()
    assert '"agent"' in text
    assert '"tasks"' in text
