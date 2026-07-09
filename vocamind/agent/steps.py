"""Agent Loop 单步逻辑。"""
from __future__ import annotations

import logging
from typing import Any, Callable

from vocamind.agent.conditions import CONTINUATION_PROMPT, DEFAULT_MAX_TOKENS
from vocamind.agent.state import AgentContext
from vocamind.llm.tool_client import (
    ToolCallingClient,
    get_tool_calls,
    has_tool_calls,
    message_text,
    parse_tool_arguments,
)
from vocamind.tools import assemble_tool_pool
from vocamind.tools.background import collect_background_results
from vocamind.tools.compact import compact_history, prepare_context, reactive_compact, set_summarizer
from vocamind.tools.cron import consume_cron_queue
from vocamind.tools.hooks import call_tool_handler, trigger_hooks
from vocamind.tools.todo import get_current_todos

logger = logging.getLogger(__name__)


def build_user_content(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content = list(results)
    for note in collect_background_results():
        content.append({"type": "text", "text": note})
    return content


def inject_background_notifications(messages: list[dict[str, Any]]) -> None:
    notes = collect_background_results()
    if notes:
        messages.append({"role": "user", "content": "\n".join(notes)})


def inject_cron_messages(messages: list[dict[str, Any]]) -> None:
    for job in consume_cron_queue():
        messages.append({"role": "user", "content": f"[Scheduled] {job.prompt}"})
        logger.info("[cron inject] %s", job.prompt[:60])


def update_context_dict() -> dict[str, Any]:
    from vocamind.tools import mcp
    from vocamind.tools.teammate import list_teammate_names

    return {
        "todos": get_current_todos(),
        "connected_mcp": mcp.list_mcp_names(),
        "active_teammates": list_teammate_names(),
    }


def call_agent_llm(
    client: ToolCallingClient,
    ctx: AgentContext,
    tools: list[dict[str, Any]],
    system_prompt: str,
) -> Any:
    prepare_context(ctx.messages)
    return client.create(
        messages=ctx.messages,
        tools=tools,
        system_prompt=system_prompt,
        max_tokens=ctx.max_tokens,
    )


def execute_tool_batch(
    ctx: AgentContext,
    assistant_message: Any,
    handlers: dict[str, Callable[..., str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ctx.compacted_now = False
    for tc in get_tool_calls(assistant_message):
        name = tc.function.name
        args = parse_tool_arguments(tc.function.arguments)
        logger.info("> %s", name)

        if name == "compact":
            ctx.messages[:] = compact_history(ctx.messages)
            ctx.messages.append({"role": "user", "content": "[Compacted. Continue with summarized context.]"})
            ctx.compacted_now = True
            break

        blocked = trigger_hooks("PreToolUse", name, args)
        if blocked:
            results.append({"role": "tool", "tool_call_id": tc.id, "content": str(blocked)})
            continue

        from vocamind.agent.conditions import should_run_background_tool
        from vocamind.tools.background import start_background_task

        if should_run_background_tool(name, args):
            bg_id = start_background_task(tc.id, name, args, handlers)
            output = f"[Background task {bg_id} started] Result will arrive as a task_notification."
        else:
            handler = handlers.get(name)
            output = call_tool_handler(handler, args, name)
            trigger_hooks("PostToolUse", name, output)
            if name == "complete_task" and output.startswith("Completed"):
                ctx.completed_by_tool = True

        results.append({"role": "tool", "tool_call_id": tc.id, "content": str(output)})

    return results


def append_assistant_message(messages: list[dict[str, Any]], assistant_message: Any) -> None:
    msg: dict[str, Any] = {"role": "assistant", "content": assistant_message.content or ""}
    if assistant_message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in assistant_message.tool_calls
        ]
    messages.append(msg)


def handle_llm_error(ctx: AgentContext, exc: Exception) -> bool:
    from vocamind.agent.conditions import should_reactive_compact

    if should_reactive_compact(exc, ctx.recovery):
        ctx.messages[:] = reactive_compact(ctx.messages)
        ctx.recovery.has_attempted_reactive_compact = True
        return True
    ctx.messages.append({"role": "assistant", "content": f"[Error] {type(exc).__name__}: {exc}"})
    ctx.failed = True
    return False


def setup_agent_tools(client: ToolCallingClient, system_prompt: str) -> tuple[list[dict], dict]:
    set_summarizer(client.summarize)
    sub_system = system_prompt + " You are a coding subagent. Return a concise summary."
    return assemble_tool_pool(
        subagent_client_factory=lambda: client,
        teammate_client_factory=lambda: client,
        subagent_system=sub_system,
    )


def extract_final_summary(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            return str(msg["content"])[:500]
    return "Task completed."
