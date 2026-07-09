"""任务存储 CRUD 测试。"""
import json
from pathlib import Path

import pytest

from vocamind.tasks.store import TaskStore


@pytest.fixture
def store(tmp_path: Path) -> TaskStore:
    return TaskStore(tasks_dir=tmp_path / ".tasks")


def test_create_and_list_tasks(store: TaskStore):
    t1 = store.create_task("任务A", "描述A")
    t2 = store.create_task("任务B", description="描述B", blockedBy=[t1.id])
    tasks = store.list_tasks()
    assert len(tasks) == 2
    subjects = {t.subject for t in tasks}
    assert subjects == {"任务A", "任务B"}
    assert t2.blockedBy == [t1.id]


def test_claim_and_complete(store: TaskStore):
    t = store.create_task("执行某事")
    result = store.claim_task(t.id)
    assert "Claimed" in result
    assert store.load_task(t.id).status == "in_progress"
    complete = store.complete_task(t.id)
    assert "Completed" in complete
    assert store.load_task(t.id).status == "completed"


def test_blocked_by_dependency(store: TaskStore):
    t1 = store.create_task("前置")
    t2 = store.create_task("后续", blockedBy=[t1.id])
    result = store.claim_task(t2.id)
    assert "Cannot start" in result
    store.claim_task(t1.id)
    store.complete_task(t1.id)
    result2 = store.claim_task(t2.id)
    assert "Claimed" in result2


def test_get_task_json(store: TaskStore):
    t = store.create_task("JSON测试")
    data = json.loads(store.get_task_json(t.id))
    assert data["subject"] == "JSON测试"
    assert data["status"] == "pending"
    assert data["created_at"]
    assert data["updated_at"]


def test_task_file_utf8_and_timestamps(store: TaskStore):
    t = store.create_task("世界杯报告", "写一份中文文档")
    raw = (store.tasks_dir / f"{t.id}.json").read_text(encoding="utf-8")
    assert "世界杯报告" in raw
    assert "\\u" not in raw
    loaded = store.load_task(t.id)
    assert loaded.created_at
    assert loaded.updated_at
    created_at = loaded.created_at
    store.claim_task(t.id)
    after_claim = store.load_task(t.id)
    assert after_claim.updated_at >= created_at
