"""WebSocket 工具调用事件（供客户端展示 Agent 式工具卡片）。"""
from __future__ import annotations

from typing import Any, Optional

TOOL_EVENT_TYPE = "tool_event"
CONTENT_PREVIEW_MAX = 800


def is_tool_event(message: dict[str, Any]) -> bool:
    return message.get("type") == TOOL_EVENT_TYPE


def preview_tool_content(text: str, limit: int = CONTENT_PREVIEW_MAX) -> str:
    body = str(text or "")
    if len(body) <= limit:
        return body
    return body[:limit] + f"\n…（共 {len(body)} 字符）"


def build_tool_start(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    scope: str,
    uid: Optional[str],
    user_input_count: int,
    proactive: bool = False,
    task_id: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "type": TOOL_EVENT_TYPE,
        "event": "start",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "scope": scope,
        "task_id": task_id,
        "uid": uid,
        "user_input_count": user_input_count,
        "proactive": proactive,
    }


def build_tool_end(
    *,
    tool_call_id: str,
    tool_name: str,
    status: str,
    content: str,
    scope: str,
    uid: Optional[str],
    user_input_count: int,
    proactive: bool = False,
    task_id: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "type": TOOL_EVENT_TYPE,
        "event": "end",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "status": status,
        "content": content,
        "content_preview": preview_tool_content(content),
        "scope": scope,
        "task_id": task_id,
        "uid": uid,
        "user_input_count": user_input_count,
        "proactive": proactive,
    }
