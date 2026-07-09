"""任务队列测试。"""
import threading
import time

from vocamind.tasks.queue import AgentTaskMessage, AgentTaskQueue


def test_enqueue_dequeue():
    q = AgentTaskQueue()
    msg = AgentTaskMessage(
        task_id="task_001",
        subject="测试",
        description="做某事",
        source="voice",
        user_input_count=1,
        uid="u1",
    )
    q.enqueue(msg)
    assert q.pending_count == 1
    got = q.dequeue(block=False)
    assert got.task_id == "task_001"
    assert q.pending_count == 0


def test_notifications_failed():
    q = AgentTaskQueue()
    q.notify_complete("t1", "auth error", status="failed")
    notes = q.format_notifications_for_voice()
    assert notes[0].startswith("[TaskFailed]")


def test_notifications_done():
    q = AgentTaskQueue()
    q.notify_complete("task_001", "已完成摘要")
    notes = q.format_notifications_for_voice()
    assert len(notes) == 1
    assert "[TaskDone] task_001" in notes[0]


def test_blocking_dequeue():
    q = AgentTaskQueue()
    result: list[AgentTaskMessage] = []

    def consumer():
        result.append(q.dequeue(timeout=2.0))

    t = threading.Thread(target=consumer, daemon=True)
    t.start()
    time.sleep(0.1)
    q.enqueue(AgentTaskMessage("t1", "s", "d", "voice"))
    t.join(timeout=3)
    assert len(result) == 1
