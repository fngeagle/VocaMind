"""Subagent 迷你 loop。"""
from __future__ import annotations

from typing import Any, Callable

from vocamind.llm.tool_client import ToolCallingClient, get_tool_calls, has_tool_calls, message_text, parse_tool_arguments
from vocamind.tools.builtin import run_bash, run_edit, run_glob, run_read, run_write
from vocamind.tools.hooks import call_tool_handler, trigger_hooks

SUB_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}, "offset": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

SUB_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}


def spawn_subagent(description: str, client: ToolCallingClient, system_prompt: str) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": description}]
    for _ in range(30):
        response = client.create(
            messages=messages,
            tools=SUB_TOOLS,
            system_prompt=system_prompt,
            max_tokens=8000,
        )
        assistant = response.choices[0].message
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": assistant.content or ""}
        if assistant.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in assistant.tool_calls
            ]
        messages.append(assistant_msg)
        if not has_tool_calls(assistant):
            return message_text(assistant) or "Subagent finished."
        for tc in get_tool_calls(assistant):
            name = tc.function.name
            args = parse_tool_arguments(tc.function.arguments)
            blocked = trigger_hooks("PreToolUse", name, args)
            if blocked:
                output = str(blocked)
            else:
                handler = SUB_HANDLERS.get(name)
                output = call_tool_handler(handler, args, name)
                trigger_hooks("PostToolUse", name, output)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(output)})
    return "Subagent finished without a text summary."
