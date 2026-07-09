"""任务持久化：文件-backed Task CRUD（移植自 example.py）。"""
from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from vocamind.common.paths import PROJECT_ROOT

DEFAULT_TASKS_DIR = PROJECT_ROOT / ".tasks"


def _now_iso() -> str:
    """返回带时区的 ISO 8601 时间字符串。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str
    owner: Optional[str]
    blockedBy: list[str]
    worktree: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


def _task_from_dict(data: dict) -> Task:
    """从 JSON 字典构造 Task，兼容缺少时间字段的旧文件。"""
    return Task(
        id=data["id"],
        subject=data["subject"],
        description=data.get("description", ""),
        status=data["status"],
        owner=data.get("owner"),
        blockedBy=data.get("blockedBy") or [],
        worktree=data.get("worktree"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def _format_task_json(task: Task) -> str:
    """序列化为 UTF-8 可读 JSON（中文不转义）。"""
    return json.dumps(asdict(task), indent=2, ensure_ascii=False) + "\n"


class TaskStore:
    """基于 JSON 文件的任务存储。"""

    def __init__(self, tasks_dir: Path | None = None) -> None:
        self.tasks_dir = tasks_dir or DEFAULT_TASKS_DIR
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def create_task(
        self,
        subject: str,
        description: str = "",
        blockedBy: list[str] | None = None,
    ) -> Task:
        now = _now_iso()
        task = Task(
            id=f"task_{int(time.time())}_{random.randint(0, 9999):04d}",
            subject=subject,
            description=description,
            status="pending",
            owner=None,
            blockedBy=blockedBy or [],
            created_at=now,
            updated_at=now,
        )
        self.save_task(task, touch_updated_at=False)
        return task

    def save_task(self, task: Task, *, touch_updated_at: bool = True) -> None:
        if touch_updated_at:
            task.updated_at = _now_iso()
            if not task.created_at:
                task.created_at = task.updated_at
        self._task_path(task.id).write_text(
            _format_task_json(task),
            encoding="utf-8",
        )

    def load_task(self, task_id: str) -> Task:
        return _task_from_dict(
            json.loads(self._task_path(task_id).read_text(encoding="utf-8"))
        )

    def list_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for path in sorted(self.tasks_dir.glob("task_*.json")):
            tasks.append(
                _task_from_dict(json.loads(path.read_text(encoding="utf-8")))
            )
        return tasks

    def get_task_json(self, task_id: str) -> str:
        return _format_task_json(self.load_task(task_id)).rstrip("\n")

    def can_start(self, task_id: str) -> bool:
        task = self.load_task(task_id)
        for dep_id in task.blockedBy:
            if not self._task_path(dep_id).exists():
                return False
            if self.load_task(dep_id).status != "completed":
                return False
        return True

    def claim_task(self, task_id: str, owner: str = "agent") -> str:
        task = self.load_task(task_id)
        if task.status != "pending":
            return f"Task {task_id} is {task.status}, cannot claim"
        if task.owner:
            return f"Task {task_id} already owned by {task.owner}"
        if not self.can_start(task_id):
            deps = [
                d
                for d in task.blockedBy
                if self._task_path(d).exists() and self.load_task(d).status != "completed"
            ]
            missing = [d for d in task.blockedBy if not self._task_path(d).exists()]
            parts = []
            if deps:
                parts.append(f"blocked by: {deps}")
            if missing:
                parts.append(f"missing deps: {missing}")
            return "Cannot start — " + ", ".join(parts)
        task.owner = owner
        task.status = "in_progress"
        self.save_task(task)
        return f"Claimed {task.id} ({task.subject})"

    def complete_task(self, task_id: str) -> str:
        task = self.load_task(task_id)
        if task.status != "in_progress":
            return f"Task {task_id} is {task.status}, cannot complete"
        task.status = "completed"
        self.save_task(task)
        unblocked = [
            t.subject
            for t in self.list_tasks()
            if t.status == "pending" and t.blockedBy and self.can_start(t.id)
        ]
        msg = f"Completed {task.id} ({task.subject})"
        if unblocked:
            msg += f"\nUnblocked: {', '.join(unblocked)}"
        return msg

    def fail_task(self, task_id: str, reason: str = "") -> str:
        task = self.load_task(task_id)
        if task.status not in ("in_progress", "pending"):
            return f"Task {task_id} is {task.status}, cannot fail"
        task.status = "failed"
        task.owner = None
        self.save_task(task)
        brief = reason[:200] if reason else "agent failed"
        return f"Failed {task.id} ({task.subject}): {brief}"


_default_store: TaskStore | None = None


def get_task_store(tasks_dir: Path | None = None) -> TaskStore:
    global _default_store
    if tasks_dir is not None:
        _default_store = TaskStore(tasks_dir)
        return _default_store
    if _default_store is None:
        _default_store = TaskStore()
    return _default_store


def create_task(subject: str, description: str = "", blockedBy: list[str] | None = None) -> Task:
    return get_task_store().create_task(subject, description, blockedBy)


def list_tasks() -> list[Task]:
    return get_task_store().list_tasks()


def get_task_json(task_id: str) -> str:
    return get_task_store().get_task_json(task_id)


def claim_task(task_id: str, owner: str = "agent") -> str:
    return get_task_store().claim_task(task_id, owner)


def complete_task(task_id: str) -> str:
    return get_task_store().complete_task(task_id)


def fail_task(task_id: str, reason: str = "") -> str:
    return get_task_store().fail_task(task_id, reason)


def list_tasks_summary() -> str:
    """供 Voice 查询：按时间倒序列出任务及中文状态。"""
    status_cn = {
        "pending": "待处理",
        "in_progress": "进行中",
        "completed": "已完成",
        "failed": "失败",
    }
    tasks = sorted(get_task_store().list_tasks(), key=lambda t: t.id, reverse=True)
    if not tasks:
        return "No tasks."
    return "\n".join(
        f"  {t.id}: {t.subject} [{status_cn.get(t.status, t.status)}]"
        for t in tasks
    )
