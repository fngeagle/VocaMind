"""LLM 流式推理的终止与分支条件。"""
from __future__ import annotations

from threading import Event


def should_abort_stream(interruption_event: Event) -> bool:
    return interruption_event.is_set()


def should_emit_interruption_transition(interruption_event: Event) -> bool:
    return interruption_event.is_set()
