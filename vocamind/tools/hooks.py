"""Hooks 与权限管道。"""
from __future__ import annotations

from typing import Any, Callable, Optional

HOOKS: dict[str, list[Callable[..., Optional[str]]]] = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}


def register_hook(event: str, callback: Callable[..., Optional[str]]) -> None:
    HOOKS.setdefault(event, []).append(callback)


def trigger_hooks(event: str, *args: Any) -> Optional[str]:
    for callback in HOOKS.get(event, []):
        result = callback(*args)
        if result is not None:
            return result
    return None


DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]


def permission_hook(tool_name: str, tool_input: dict[str, Any]) -> Optional[str]:
    if tool_name == "bash":
        command = tool_input.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                return f"Permission denied: '{pattern}' is on the deny list"
        if any(token in command for token in DESTRUCTIVE):
            return "Permission denied: destructive command blocked in server mode"
    if tool_name in ("write_file", "edit_file"):
        path = tool_input.get("path", "")
        try:
            from vocamind.tools.builtin import safe_path
            safe_path(path)
        except Exception:
            return f"Permission denied: path escapes workspace: {path}"
    if tool_name.startswith("mcp__") and "deploy" in tool_name:
        return None
    return None


def log_hook(tool_name: str, tool_input: dict[str, Any]) -> None:
    import logging

    logging.getLogger(__name__).debug("[HOOK] %s %s", tool_name, tool_input)


def large_output_hook(tool_name: str, output: str) -> None:
    if len(str(output)) > 100000:
        import logging

        logging.getLogger(__name__).warning(
            "[HOOK] large output from %s: %d chars", tool_name, len(str(output))
        )


def stop_hook(messages: list[dict[str, Any]]) -> None:
    import logging

    tool_count = sum(
        1
        for msg in messages
        if msg.get("role") == "tool"
    )
    logging.getLogger(__name__).debug("[HOOK] Stop: %d tool result(s)", tool_count)


def register_default_hooks() -> None:
    HOOKS["PreToolUse"] = [permission_hook]
    HOOKS["PostToolUse"] = [large_output_hook]
    HOOKS["Stop"] = [stop_hook]


def call_tool_handler(handler: Callable[..., str] | None, args: dict[str, Any], name: str) -> str:
    if not handler:
        return f"Unknown: {name}"
    try:
        return handler(**(args or {}))
    except TypeError as exc:
        return f"Error: {exc}"
