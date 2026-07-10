"""Agent 任务队列：Voice LLM 派发与 Agent Loop 消费之间的桥梁。"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class AgentTaskMessage:
    task_id: str
    subject: str
    description: str
    source: str  # "voice" | "cron" | "internal"
    user_input_count: int = 0
    uid: Optional[str] = None


@dataclass
class TaskNotification:
    """任务完成通知，供 Voice LLM 下一轮注入。"""

    task_id: str
    summary: str
    status: str = "completed"
    user_input_count: int = 0
    uid: Optional[str] = None
    attachments: list[dict[str, str]] | None = None


def format_notification_line(note: TaskNotification) -> str:
    """将任务通知格式化为 Voice 可消费的文本。"""
    if note.status == "failed":
        return f"[TaskFailed] {note.task_id}: {note.summary}"
    if note.status == "in_progress":
        return f"[TaskRunning] {note.task_id}: {note.summary}"
    return f"[TaskDone] {note.task_id}: {note.summary}"


class AgentTaskQueue:
    """线程安全的任务入队/出队与完成通知。"""

    def __init__(self) -> None:
        self._queue: queue.Queue[AgentTaskMessage] = queue.Queue()
        self._notifications: queue.Queue[TaskNotification] = queue.Queue()
        self._lock = threading.Lock()
        self._pending_count = 0
        self._task_context: dict[str, tuple[int, Optional[str]]] = {}
        self._on_notification: Optional[Callable[[TaskNotification], None]] = None

    def set_notification_handler(self, handler: Callable[[TaskNotification], None]) -> None:
        """注册任务完成时的主动推送回调。"""
        self._on_notification = handler

    def enqueue(self, message: AgentTaskMessage) -> None:
        with self._lock:
            self._pending_count += 1
            self._task_context[message.task_id] = (message.user_input_count, message.uid)
        self._queue.put(message)

    def dequeue(self, block: bool = True, timeout: float | None = None) -> AgentTaskMessage:
        if block and timeout is None:
            msg = self._queue.get()
        else:
            msg = self._queue.get(block=block, timeout=timeout)
        with self._lock:
            self._pending_count = max(0, self._pending_count - 1)
        return msg

    def try_dequeue(self) -> AgentTaskMessage | None:
        try:
            return self.dequeue(block=False)
        except queue.Empty:
            return None

    @property
    def pending_count(self) -> int:
        with self._lock:
            return self._pending_count

    def notify_complete(
        self,
        task_id: str,
        summary: str,
        status: str = "completed",
        attachments: list[dict[str, str]] | None = None,
    ) -> None:
        user_input_count, uid = self._task_context.pop(task_id, (0, None))
        note = TaskNotification(
            task_id=task_id,
            summary=summary,
            status=status,
            user_input_count=user_input_count,
            uid=uid,
            attachments=attachments or None,
        )
        if self._on_notification:
            self._on_notification(note)
        else:
            self._notifications.put(note)

    def drain_notifications(self) -> list[TaskNotification]:
        items: list[TaskNotification] = []
        while True:
            try:
                items.append(self._notifications.get_nowait())
            except queue.Empty:
                break
        return items

    def format_notifications_for_voice(self) -> list[str]:
        return [format_notification_line(n) for n in self.drain_notifications()]
