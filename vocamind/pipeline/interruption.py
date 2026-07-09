"""打断信号与下游队列清理。"""
from __future__ import annotations

import logging
from queue import Empty, Queue
from threading import Event

from vocamind.pipeline.state import PipelineContext

logger = logging.getLogger(__name__)


def drain_queue(queue: Queue) -> int:
    """清空队列中积压项，返回丢弃数量。"""
    count = 0
    while True:
        try:
            queue.get_nowait()
            count += 1
        except Empty:
            break
    return count


def trigger_interruption(ctx: PipelineContext) -> None:
    """置位打断事件并清理由 LLM/TTS 产生的下游积压。"""
    trigger_interruption_queues(
        ctx.interruption_event,
        ctx.lm_response_queue,
        ctx.outbound_queue,
    )


def trigger_interruption_queues(
    interruption_event: Event,
    lm_response_queue: Queue,
    outbound_queue: Queue,
) -> None:
    """置位打断事件并清空指定下游队列。"""
    interruption_event.set()
    lm_dropped = drain_queue(lm_response_queue)
    outbound_dropped = drain_queue(outbound_queue)
    if lm_dropped or outbound_dropped:
        logger.info(
            "打断已清下游队列: lm_response=%d, outbound=%d",
            lm_dropped,
            outbound_dropped,
        )
