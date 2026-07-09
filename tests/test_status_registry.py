"""状态注册表测试。"""
from pathlib import Path

from vocamind.status import StatusRegistry
from vocamind.tasks.store import get_task_store


def test_snapshot_defaults(tmp_path: Path):
    get_task_store(tmp_path / ".tasks")
    reg = StatusRegistry()
    snap = reg.snapshot()
    assert snap.agent.idle is True
    assert snap.tasks == []
    assert snap.queue_pending == 0


def test_snapshot_with_agent_and_pipeline():
    reg = StatusRegistry()
    reg.update_agent(idle=False, current_task_id="task_001", round_count=3)
    reg.update_pipeline(connected=True, should_listen=True)
    reg.set_todos([{"content": "做X", "status": "pending"}])
    reg.set_mcp(["filesystem"])
    reg.set_teammates(["worker1"])
    reg.set_queue_pending(2)
    snap = reg.snapshot()
    assert snap.agent.current_task_id == "task_001"
    assert snap.pipeline.connected is True
    assert len(snap.todos) == 1
    assert snap.mcp == ["filesystem"]
    assert snap.queue_pending == 2


def test_snapshot_json():
    reg = StatusRegistry()
    text = reg.snapshot_json()
    assert '"agent"' in text
    assert '"tasks"' in text
