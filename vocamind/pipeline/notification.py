"""后台任务完成通知 → Voice 管道主动推送。"""
from __future__ import annotations

import logging

from vocamind.pipeline.attachments import take_pending_attachments
from vocamind.pipeline.interruption import trigger_interruption
from vocamind.pipeline.state import PipelineContext
from vocamind.tasks.queue import TaskNotification, format_notification_line

logger = logging.getLogger(__name__)


def forward_task_notification(ctx: PipelineContext, note: TaskNotification) -> None:
    """将任务完成通知注入 Voice 输入队列，必要时打断当前轮次。"""
    if not note.uid:
        logger.debug("任务 %s 完成但无 uid，跳过主动推送", note.task_id)
        return

    line = format_notification_line(note)
    if ctx.assistant_turn_active.is_set():
        trigger_interruption(ctx)
        ctx.outbound_queue.put({"stop_playback": True, "uid": note.uid})

    if note.attachments:
        ctx.pending_attachments[note.uid] = list(note.attachments)
        ctx.outbound_queue.put(
            {
                "uid": note.uid,
                "user_input_count": note.user_input_count,
                "proactive": True,
                "attachments": note.attachments,
                "end_flag": False,
            }
        )

    ctx.text_prompt_queue.put(
        {
            "data": line,
            "user_input_count": note.user_input_count,
            "uid": note.uid,
            "audio_input": False,
            "proactive": True,
        }
    )
    logger.info("主动推送任务通知: %s", line[:80])
