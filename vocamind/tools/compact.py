"""上下文压缩管线。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from vocamind.common.paths import PROJECT_ROOT

TRANSCRIPT_DIR = PROJECT_ROOT / ".transcripts"
TOOL_RESULTS_DIR = PROJECT_ROOT / ".task_outputs" / "tool-results"
CONTEXT_LIMIT = 50000
KEEP_RECENT_TOOL_RESULTS = 3
PERSIST_THRESHOLD = 30000

_summarizer: Optional[Callable[[str], str]] = None


def set_summarizer(fn: Callable[[str], str]) -> None:
    global _summarizer
    _summarizer = fn


def estimate_size(messages: list[dict[str, Any]]) -> int:
    return len(json.dumps(messages, default=str))


def message_has_tool_use(message: dict[str, Any]) -> bool:
    if message.get("role") != "assistant":
        return False
    return bool(getattr(message.get("_tool_calls"), "__iter__", False) or message.get("tool_calls"))


def is_tool_result_message(message: dict[str, Any]) -> bool:
    return message.get("role") == "tool"


def collect_tool_results(messages: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    found = []
    for mi, msg in enumerate(messages):
        if msg.get("role") == "tool":
            found.append((mi, msg))
    return found


def persist_large_output(tool_call_id: str, output: str) -> str:
    if len(output) <= PERSIST_THRESHOLD:
        return output
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOOL_RESULTS_DIR / f"{tool_call_id}.txt"
    if not path.exists():
        path.write_text(output, encoding="utf-8")
    return (
        f"<persisted-output>\nFull output: {path}\nPreview:\n{output[:2000]}\n</persisted-output>"
    )


def tool_result_budget(messages: list[dict[str, Any]], max_bytes: int = 200_000) -> list[dict[str, Any]]:
    if not messages:
        return messages
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    total = sum(len(str(m.get("content", ""))) for m in tool_msgs)
    if total <= max_bytes:
        return messages
    for msg in sorted(tool_msgs, key=lambda m: len(str(m.get("content", ""))), reverse=True):
        if total <= max_bytes:
            break
        text = str(msg.get("content", ""))
        msg["content"] = persist_large_output(msg.get("tool_call_id", "unknown"), text)
        total = sum(len(str(m.get("content", ""))) for m in tool_msgs)
    return messages


def snip_compact(messages: list[dict[str, Any]], max_messages: int = 50) -> list[dict[str, Any]]:
    if len(messages) <= max_messages:
        return messages
    head_end, tail_start = 3, len(messages) - (max_messages - 3)
    if head_end >= tail_start:
        return messages
    snipped = tail_start - head_end
    return (
        messages[:head_end]
        + [{"role": "user", "content": f"[snipped {snipped} messages]"}]
        + messages[tail_start:]
    )


def micro_compact(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_results = collect_tool_results(messages)
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages
    for _, block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        if len(str(block.get("content", ""))) > 120:
            block["content"] = "[Earlier tool result compacted. Re-run if needed.]"
    return messages


def write_transcript(messages: list[dict[str, Any]]) -> Path:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    return path


def summarize_history(messages: list[dict[str, Any]]) -> str:
    conversation = json.dumps(messages, default=str)[:80000]
    prompt = (
        "Summarize this coding-agent conversation so work can continue. "
        "Preserve current goal, key findings, changed files, remaining work, "
        "and user constraints.\n\n"
        + conversation
    )
    if _summarizer:
        return _summarizer(prompt)
    return "(compaction unavailable: no summarizer configured)"


def compact_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    write_transcript(messages)
    summary = summarize_history(messages)
    return [{"role": "user", "content": f"[Compacted]\n\n{summary}"}]


def reactive_compact(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    write_transcript(messages)
    tail_start = max(0, len(messages) - 5)
    try:
        summary = summarize_history(messages[:tail_start])
    except Exception:
        summary = "Earlier conversation was trimmed after a prompt-too-long error."
    return [{"role": "user", "content": f"[Reactive compact]\n\n{summary}"}, *messages[tail_start:]]


def prepare_context(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages[:] = tool_result_budget(messages)
    messages[:] = snip_compact(messages)
    messages[:] = micro_compact(messages)
    if estimate_size(messages) > CONTEXT_LIMIT:
        messages[:] = compact_history(messages)
    return messages
