"""后台 bash 任务。"""
from __future__ import annotations

import threading
from typing import Any, Callable

from vocamind.tools.hooks import call_tool_handler, trigger_hooks

_bg_counter = 0
background_tasks: dict[str, dict[str, Any]] = {}
background_results: dict[str, str] = {}
background_lock = threading.Lock()


def is_slow_operation(tool_name: str, tool_input: dict[str, Any]) -> bool:
    if tool_name != "bash":
        return False
    command = tool_input.get("command", "").lower()
    slow_keywords = [
        "install", "build", "test", "deploy", "compile",
        "docker build", "pip install", "npm install",
        "cargo build", "pytest", "make",
    ]
    return any(keyword in command for keyword in slow_keywords)


def should_run_background(tool_name: str, tool_input: dict[str, Any]) -> bool:
    if tool_name != "bash":
        return False
    return bool(tool_input.get("run_in_background")) or is_slow_operation(tool_name, tool_input)


def start_background_task(
    tool_call_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    handlers: dict[str, Callable[..., str]],
) -> str:
    global _bg_counter
    _bg_counter += 1
    bg_id = f"bg_{_bg_counter:04d}"
    command = tool_input.get("command", tool_name)

    def worker() -> None:
        handler = handlers.get(tool_name)
        result = call_tool_handler(handler, tool_input, tool_name)
        trigger_hooks("PostToolUse", tool_name, result)
        with background_lock:
            background_tasks[bg_id]["status"] = "completed"
            background_results[bg_id] = str(result)

    with background_lock:
        background_tasks[bg_id] = {
            "tool_call_id": tool_call_id,
            "command": command,
            "status": "running",
        }
    threading.Thread(target=worker, daemon=True).start()
    return bg_id


def collect_background_results() -> list[str]:
    with background_lock:
        ready = [bg_id for bg_id, task in background_tasks.items() if task["status"] == "completed"]
    notifications = []
    for bg_id in ready:
        with background_lock:
            task = background_tasks.pop(bg_id)
            output = background_results.pop(bg_id, "")
        summary = output[:200] if len(output) > 200 else output
        notifications.append(
            f"<task_notification>\n"
            f"  <task_id>{bg_id}</task_id>\n"
            f"  <status>completed</status>\n"
            f"  <command>{task['command']}</command>\n"
            f"  <summary>{summary}</summary>\n"
            f"</task_notification>"
        )
    return notifications


def get_background_state() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    with background_lock:
        return dict(background_tasks), dict(background_results)
