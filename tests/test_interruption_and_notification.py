"""打断与任务通知推送测试。"""
from queue import Empty
from unittest.mock import MagicMock

from vocamind.pipeline.interruption import drain_queue, trigger_interruption_queues
from vocamind.pipeline.notification import forward_task_notification
from vocamind.pipeline.state import PipelineContext
from vocamind.tasks.queue import AgentTaskMessage, AgentTaskQueue, TaskNotification


def test_drain_queue():
    ctx = PipelineContext.create()
    ctx.lm_response_queue.put({"x": 1})
    assert drain_queue(ctx.lm_response_queue) == 1
    with __import__("pytest").raises(Empty):
        ctx.lm_response_queue.get_nowait()


def test_trigger_interruption_clears_downstream():
    ctx = PipelineContext.create()
    ctx.lm_response_queue.put({"a": 1})
    ctx.outbound_queue.put({"b": 2})
    trigger_interruption_queues(ctx.interruption_event, ctx.lm_response_queue, ctx.outbound_queue)
    assert ctx.interruption_event.is_set()
    assert drain_queue(ctx.lm_response_queue) == 0
    assert drain_queue(ctx.outbound_queue) == 0


def test_forward_task_notification_enqueues_proactive_turn():
    ctx = PipelineContext.create()
    note = TaskNotification(
        task_id="t1",
        summary="报告写好了",
        status="completed",
        user_input_count=3,
        uid="u1",
    )
    forward_task_notification(ctx, note)
    item = ctx.text_prompt_queue.get(timeout=0.5)
    assert item["proactive"] is True
    assert "[TaskDone]" in item["data"]
    assert item["uid"] == "u1"


def test_notify_complete_invokes_handler():
    q = AgentTaskQueue()
    received: list[TaskNotification] = []
    q.set_notification_handler(received.append)
    q.enqueue(
        AgentTaskMessage(
            task_id="task_001",
            subject="测试",
            description="做某事",
            source="voice",
            user_input_count=2,
            uid="u9",
        )
    )
    q.notify_complete("task_001", "已完成摘要")
    assert len(received) == 1
    assert received[0].uid == "u9"
    assert received[0].user_input_count == 2
    assert q.format_notifications_for_voice() == []
