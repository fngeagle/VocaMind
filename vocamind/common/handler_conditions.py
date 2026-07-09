"""Handler 事件循环的终止与空闲分支条件。"""
from __future__ import annotations

import time
from threading import Event
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vocamind.common.handler import BaseHandler


def should_continue_handler(stop_event: Event) -> bool:
    return not stop_event.is_set()


def should_flush_on_idle(cur_conn_end_event: Event) -> bool:
    return cur_conn_end_event.is_set()


def handle_queue_idle(handler: BaseHandler) -> None:
    """队列空闲时：若会话 flush 已请求，则清空 Handler 积压。"""
    if should_flush_on_idle(handler.cur_conn_end_event):
        handler.clear_current_state()
        time.sleep(0.1)
