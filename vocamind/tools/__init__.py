"""Agent 工具池组装。"""
from __future__ import annotations

from typing import Any, Callable

from vocamind.tasks import claim_task, complete_task, create_task, get_task_json, list_tasks
from vocamind.tools import builtin, mcp, subagent, teammate
from vocamind.tools.background import should_run_background, start_background_task
from vocamind.tools.cron import run_cancel_cron, run_list_crons, run_schedule_cron
from vocamind.tools.hooks import call_tool_handler
from vocamind.tools.todo import run_todo_write

BUILTIN_TOOLS: list[dict[str, Any]] = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "run_in_background": {"type": "boolean"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}, "offset": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "todo_write", "description": "Create and manage a task list for the current session.",
     "input_schema": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
    {"name": "compact", "description": "Summarize earlier conversation and continue with compacted context.",
     "input_schema": {"type": "object", "properties": {"focus": {"type": "string"}}, "required": []}},
    {"name": "create_task", "description": "Create a task.",
     "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}, "blockedBy": {"type": "array", "items": {"type": "string"}}}, "required": ["subject"]}},
    {"name": "list_tasks", "description": "List all tasks.", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_task", "description": "Get full task details.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    {"name": "claim_task", "description": "Claim a pending task.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    {"name": "complete_task", "description": "Complete an in-progress task.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
    {"name": "schedule_cron", "description": "Schedule a cron job (5-field cron).",
     "input_schema": {"type": "object", "properties": {"cron": {"type": "string"}, "prompt": {"type": "string"}, "recurring": {"type": "boolean"}, "durable": {"type": "boolean"}}, "required": ["cron", "prompt"]}},
    {"name": "list_crons", "description": "List registered cron jobs.", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "cancel_cron", "description": "Cancel a cron job by ID.",
     "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "spawn_teammate", "description": "Spawn an autonomous teammate.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "send_message", "description": "Send message to a teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}}, "required": ["to", "content"]}},
    {"name": "check_inbox", "description": "Check inbox for messages and protocol responses.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "request_shutdown", "description": "Request a teammate to shut down.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "request_plan", "description": "Ask a teammate to submit a plan.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}, "task": {"type": "string"}}, "required": ["teammate", "task"]}},
    {"name": "review_plan", "description": "Approve or reject a submitted plan.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
    {"name": "connect_mcp", "description": "Connect to an MCP server.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "task", "description": "Launch a focused subagent. Returns only its final summary.",
     "input_schema": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}},
]


def _run_create_task(subject: str, description: str = "", blockedBy: list[str] | None = None) -> str:
    task = create_task(subject, description, blockedBy)
    deps = f" (blockedBy: {', '.join(blockedBy)})" if blockedBy else ""
    return f"Created {task.id}: {task.subject}{deps}"


def _run_list_tasks() -> str:
    tasks = list_tasks()
    if not tasks:
        return "No tasks."
    return "\n".join(f"  {t.id}: {t.subject} [{t.status}]" for t in tasks)


def _run_get_task(task_id: str) -> str:
    try:
        return get_task_json(task_id)
    except FileNotFoundError:
        return f"Error: task {task_id} not found"


def _run_claim_task(task_id: str) -> str:
    try:
        return claim_task(task_id, owner="agent")
    except FileNotFoundError:
        return f"Error: task {task_id} not found"


def _run_complete_task(task_id: str) -> str:
    try:
        return complete_task(task_id)
    except FileNotFoundError:
        return f"Error: task {task_id} not found"


def assemble_tool_pool(
    *,
    subagent_client_factory: Callable[[], Any] | None = None,
    teammate_client_factory: Callable[[], Any] | None = None,
    subagent_system: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Callable[..., str]]]:
    handlers: dict[str, Callable[..., str]] = {
        "bash": builtin.run_bash,
        "read_file": builtin.run_read,
        "write_file": builtin.run_write,
        "edit_file": builtin.run_edit,
        "glob": builtin.run_glob,
        "todo_write": run_todo_write,
        "create_task": _run_create_task,
        "list_tasks": _run_list_tasks,
        "get_task": _run_get_task,
        "claim_task": _run_claim_task,
        "complete_task": _run_complete_task,
        "schedule_cron": run_schedule_cron,
        "list_crons": run_list_crons,
        "cancel_cron": run_cancel_cron,
        "send_message": teammate.run_send_message,
        "check_inbox": teammate.run_check_inbox,
        "request_shutdown": teammate.run_request_shutdown,
        "request_plan": teammate.run_request_plan,
        "review_plan": teammate.run_review_plan,
        "connect_mcp": mcp.connect_mcp,
    }
    if subagent_client_factory:
        client = subagent_client_factory()

        def _run_task(description: str) -> str:
            return subagent.spawn_subagent(description, client, subagent_system)

        handlers["task"] = _run_task
    if teammate_client_factory:
        factory = teammate_client_factory

        def _run_spawn_teammate(name: str, role: str, prompt: str) -> str:
            return teammate.run_spawn_teammate(name, role, prompt, factory)

        handlers["spawn_teammate"] = _run_spawn_teammate

    tools = list(BUILTIN_TOOLS)
    mcp_tools, mcp_handlers = mcp.assemble_mcp_tools()
    tools.extend(mcp_tools)
    handlers.update(mcp_handlers)
    return tools, handlers


__all__ = [
    "BUILTIN_TOOLS",
    "assemble_tool_pool",
    "call_tool_handler",
    "should_run_background",
    "start_background_task",
]
