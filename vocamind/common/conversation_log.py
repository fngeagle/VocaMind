"""对话上下文持久化：Voice 轮次与 Agent 任务保存为 UTF-8 JSON。"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from vocamind.common.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_CONVERSATIONS_DIR = PROJECT_ROOT / ".conversations"
CONTENT_PREVIEW_LIMIT = 8000

_conversations_dir: Path | None = None


def get_conversations_dir(base: Path | None = None) -> Path:
    """获取对话存档根目录。"""
    global _conversations_dir
    if base is not None:
        _conversations_dir = base
        return base
    if _conversations_dir is None:
        _conversations_dir = DEFAULT_CONVERSATIONS_DIR
    return _conversations_dir


def now_iso() -> str:
    """返回带时区的 ISO 8601 时间字符串。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _truncate(text: str, limit: int = CONTENT_PREVIEW_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [已截断，共 {len(text)} 字符]"


def extract_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 messages 中提取全部 tool_calls。"""
    calls: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            calls.append(
                {
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments"),
                }
            )
    return calls


def serialize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """序列化 LLM messages；超大 tool 输出保留 preview 与原始长度。"""
    result: list[dict[str, Any]] = []
    for msg in messages:
        item = dict(msg)
        content = item.get("content")
        if item.get("role") == "tool" and isinstance(content, str) and len(content) > CONTENT_PREVIEW_LIMIT:
            item["content_length"] = len(content)
            item["content"] = _truncate(content)
        result.append(item)
    return result


def build_voice_record(
    *,
    state: Any,
    system_prompt: str,
) -> dict[str, Any]:
    """构造 Voice 轮次存档结构。"""
    finished_at = now_iso()
    return {
        "kind": "voice_turn",
        "turn_id": f"voice_{int(time.time())}_{state.uid or 'unknown'}_{state.user_input_count}",
        "created_at": state.started_at or finished_at,
        "finished_at": finished_at,
        "uid": state.uid,
        "user_input_count": state.user_input_count,
        "proactive": state.proactive,
        "audio_input": state.audio_input,
        "input": {
            "user_text": state.prompt,
        },
        "system_prompt": system_prompt,
        "llm_messages": serialize_messages(state.messages),
        "outputs": {
            "assistant_raw": state.assistant_raw,
            "assistant_stream_merged": state.assistant_raw,
            "assistant_spoken": state.assistant_spoken,
            "interrupted": state.interrupted,
        },
        "tool_calls": extract_tool_calls(state.messages),
        "tool_rounds": state.tool_round,
    }


def build_agent_record(
    *,
    task_id: str,
    subject: str,
    description: str,
    source: str,
    uid: Optional[str],
    user_input_count: int,
    messages: list[dict[str, Any]],
    summary: str,
    system_prompt: str,
    started_at: str,
    round_count: int,
    failed: bool,
) -> dict[str, Any]:
    """构造 Agent 任务存档结构。"""
    assistant_raw_final = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            assistant_raw_final = str(msg["content"])
            break

    return {
        "kind": "agent_task",
        "task_id": task_id,
        "created_at": started_at,
        "finished_at": now_iso(),
        "source": source,
        "uid": uid,
        "user_input_count": user_input_count,
        "input": {
            "subject": subject,
            "description": description,
        },
        "system_prompt": system_prompt,
        "llm_messages": serialize_messages(messages),
        "outputs": {
            "assistant_raw_final": assistant_raw_final,
            "summary": summary,
            "failed": failed,
            "round_count": round_count,
        },
        "tool_calls": extract_tool_calls(messages),
    }


def save_voice_turn(record: dict[str, Any]) -> Path:
    """保存 Voice 轮次 JSON。"""
    uid = str(record.get("uid") or "unknown")[:8]
    count = record.get("user_input_count", 0)
    ts = int(time.time())
    path = _write_json(
        get_conversations_dir() / "voice" / f"voice_{ts}_{uid}_{count}.json",
        record,
    )
    logger.info("已保存 Voice 对话上下文: %s", path.name)
    return path


def save_agent_task(record: dict[str, Any]) -> Path:
    """保存 Agent 任务 JSON（按 task_id 命名）。"""
    task_id = str(record.get("task_id") or "unknown")
    path = _write_json(get_conversations_dir() / "agent" / f"{task_id}.json", record)
    logger.info("已保存 Agent 对话上下文: %s", path.name)
    return path
