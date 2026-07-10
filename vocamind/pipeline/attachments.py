"""出站消息中的文档附件合并。"""
from __future__ import annotations

from typing import Any


def take_pending_attachments(store: dict[str, list[dict[str, str]]], uid: str | None) -> list[dict[str, str]] | None:
    if not uid:
        return None
    return store.pop(str(uid), None)


def with_attachments(payload: dict[str, Any], attachments: list[dict[str, str]] | None) -> dict[str, Any]:
    if not attachments:
        return payload
    merged = dict(payload)
    merged["attachments"] = attachments
    return merged
