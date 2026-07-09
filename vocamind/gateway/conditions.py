"""WebSocket 网关服务循环的终止与分支条件。"""
from __future__ import annotations

from threading import Event


def should_stop_gateway(stop_event: Event) -> bool:
    return stop_event.is_set()


def should_continue_gateway(stop_event: Event) -> bool:
    return not stop_event.is_set()


def should_retry_after_bind_error(exc: BaseException) -> bool:
    return isinstance(exc, OSError)
