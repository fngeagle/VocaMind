"""管道各环节耗时统计与日志。"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _format_fields(fields: dict) -> str:
    if not fields:
        return ""
    parts = []
    for key, value in fields.items():
        text = str(value)
        if len(text) > 80:
            text = text[:77] + "..."
        parts.append(f"{key}={text}")
    return " " + " ".join(parts)


def log_elapsed(label: str, start: float, **fields) -> None:
    logger.info("[耗时] %s %.1f ms%s", label, elapsed_ms(start), _format_fields(fields))


@contextmanager
def timed(label: str, **fields) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        log_elapsed(label, start, **fields)
