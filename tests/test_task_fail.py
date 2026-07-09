"""任务失败状态测试。"""
import pytest
from pathlib import Path

from vocamind.tasks.store import TaskStore


@pytest.fixture
def store(tmp_path: Path) -> TaskStore:
    return TaskStore(tasks_dir=tmp_path / ".tasks")


def test_fail_task_from_in_progress(store: TaskStore):
    t = store.create_task("世界杯报告")
    store.claim_task(t.id)
    result = store.fail_task(t.id, "API 401")
    assert "Failed" in result
    loaded = store.load_task(t.id)
    assert loaded.status == "failed"
    assert loaded.owner is None


def test_list_tasks_summary_includes_failed(store: TaskStore):
    from vocamind.tasks.store import get_task_store, list_tasks_summary

    get_task_store(store.tasks_dir)
    t = store.create_task("测试")
    store.claim_task(t.id)
    store.fail_task(t.id, "error")
    summary = list_tasks_summary()
    assert "失败" in summary
    assert t.id in summary
