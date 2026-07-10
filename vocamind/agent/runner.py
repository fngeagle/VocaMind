"""Agent Loop 主体：仅串联状态、单步与终止条件。"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from vocamind.agent.conditions import (
    CONTINUATION_PROMPT,
    DEFAULT_MAX_TOKENS,
    should_continue_agent_cycle,
    should_handle_max_tokens,
    should_stop_agent,
    should_wait_for_task,
)
from vocamind.agent.state import AgentContext, AgentRuntime
from vocamind.agent.steps import (
    append_assistant_message,
    build_user_content,
    call_agent_llm,
    execute_tool_batch,
    extract_final_summary,
    handle_llm_error,
    inject_background_notifications,
    inject_cron_messages,
    setup_agent_tools,
)
from vocamind.agent.voice_summary import build_voice_delivery_summary
from vocamind.common.config import PipelineConfig
from vocamind.common.conversation_log import build_agent_record, now_iso, save_agent_task
from vocamind.llm.tool_client import ToolCallingClient, has_tool_calls, message_text
from vocamind.tasks import claim_task, complete_task, fail_task
from vocamind.tasks.queue import AgentTaskMessage
from vocamind.tools.background import get_background_state
from vocamind.tools.cron import list_cron_dicts, start_cron_scheduler
from vocamind.tools.hooks import register_default_hooks, trigger_hooks
from vocamind.tools.todo import get_current_todos
from vocamind.tools import mcp
from vocamind.tools.teammate import list_teammate_names

logger = logging.getLogger(__name__)


def _is_failure_summary(summary: str) -> bool:
    text = summary.strip()
    return (
        text.startswith("[Error]")
        or "AuthenticationError" in text
        or "Error code: 401" in text
        or "Max retries" in text
    )


def _finalize_task(
    runtime: AgentRuntime,
    task_msg: AgentTaskMessage,
    ctx: AgentContext,
    summary: str,
    attachments: list[dict[str, str]] | None = None,
) -> None:
    """根据 Agent 实际执行结果更新任务状态并通知 Voice。"""
    from vocamind.tasks.store import get_task_store

    failed = ctx.failed or _is_failure_summary(summary)
    if failed:
        fail_task(task_msg.task_id, summary)
        runtime.task_queue.notify_complete(
            task_msg.task_id, summary, status="failed", attachments=attachments
        )
        logger.warning("任务 %s 执行失败: %s", task_msg.task_id, summary[:120])
        return

    if ctx.completed_by_tool:
        runtime.task_queue.notify_complete(
            task_msg.task_id, summary, status="completed", attachments=attachments
        )
        return

    try:
        task = get_task_store().load_task(task_msg.task_id)
        if task.status == "in_progress" and ctx.round_count > 0 and not _is_failure_summary(summary):
            complete_task(task_msg.task_id)
    except FileNotFoundError:
        pass
    runtime.task_queue.notify_complete(
        task_msg.task_id, summary, status="completed", attachments=attachments
    )


def _sync_status(runtime: AgentRuntime, ctx: AgentContext | None = None) -> None:
    bg_tasks, bg_results = get_background_state()
    runtime.status_registry.set_background(bg_tasks, bg_results)
    runtime.status_registry.set_crons(list_cron_dicts())
    runtime.status_registry.set_teammates(list_teammate_names())
    runtime.status_registry.set_mcp(mcp.list_mcp_names())
    runtime.status_registry.set_todos(get_current_todos())
    runtime.status_registry.set_queue_pending(runtime.task_queue.pending_count)
    if ctx:
        runtime.status_registry.update_agent(
            idle=False,
            current_task_id=ctx.current_task_id,
            round_count=ctx.round_count,
        )


def agent_loop_for_task(
    runtime: AgentRuntime,
    client: ToolCallingClient,
    config: PipelineConfig,
    task_msg: AgentTaskMessage,
) -> str:
    """对单个任务运行完整 agent loop，返回摘要。"""
    tools, handlers = setup_agent_tools(client, config.agent_system_prompt)
    ctx = AgentContext(
        messages=[{"role": "user", "content": f"Task: {task_msg.subject}\n\n{task_msg.description}"}],
        max_tokens=config.agent_max_tokens,
        current_task_id=task_msg.task_id,
        uid=task_msg.uid,
        user_input_count=task_msg.user_input_count,
    )
    claim_task(task_msg.task_id, owner="agent")
    _sync_status(runtime, ctx)
    started_at = now_iso()

    def emit_tool_event(message: dict) -> None:
        if runtime.outbound_queue is not None:
            runtime.outbound_queue.put(message)

    while not should_stop_agent(runtime.stop_event):
        inject_cron_messages(ctx.messages)
        inject_background_notifications(ctx.messages)
        ctx.round_count += 1
        _sync_status(runtime, ctx)

        try:
            response = call_agent_llm(client, ctx, tools, config.agent_system_prompt)
        except Exception as exc:
            if handle_llm_error(ctx, exc):
                continue
            ctx.failed = True
            break

        assistant = response.choices[0].message
        append_assistant_message(ctx.messages, assistant)

        if response.choices[0].finish_reason == "length":
            cont, new_max = should_handle_max_tokens(ctx.recovery, ctx.max_tokens)
            if cont:
                ctx.max_tokens = new_max
                ctx.messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                continue
            break

        ctx.max_tokens = DEFAULT_MAX_TOKENS
        ctx.recovery.has_escalated = False

        if not should_continue_agent_cycle(ctx, assistant):
            trigger_hooks("Stop", ctx.messages)
            break

        results = execute_tool_batch(ctx, assistant, handlers, emit=emit_tool_event)
        if ctx.compacted_now:
            continue
        if results:
            ctx.messages.extend(results)

    from pathlib import Path

    from vocamind.tasks.artifacts import collect_task_artifacts, get_artifact_registry
    from vocamind.tools import builtin

    workdir = Path(config.agent_workdir) if config.agent_workdir else builtin.WORKDIR
    summary = build_voice_delivery_summary(ctx.messages, workdir=workdir)
    record_summary = extract_final_summary(ctx.messages)
    artifacts = collect_task_artifacts(
        ctx.messages, task_id=task_msg.task_id, workdir=workdir
    )
    attachment_dicts = [a.to_dict() for a in artifacts]
    if attachment_dicts:
        get_artifact_registry().register(task_msg.task_id, artifacts)
    try:
        save_agent_task(
            build_agent_record(
                task_id=task_msg.task_id,
                subject=task_msg.subject,
                description=task_msg.description,
                source=task_msg.source,
                uid=task_msg.uid,
                user_input_count=task_msg.user_input_count,
                messages=ctx.messages,
                summary=record_summary,
                system_prompt=config.agent_system_prompt,
                started_at=started_at,
                round_count=ctx.round_count,
                failed=ctx.failed or _is_failure_summary(summary),
            )
        )
    except Exception:
        logger.exception("保存 Agent 对话上下文失败")
    _finalize_task(runtime, task_msg, ctx, summary, attachment_dicts or None)
    runtime.status_registry.update_agent(idle=True, current_task_id=None, round_count=ctx.round_count)
    _sync_status(runtime)
    return summary


def run_agent_daemon(runtime: AgentRuntime, config: PipelineConfig) -> None:
    """Agent daemon：空闲等待任务队列，收到任务后运行 agent_loop。"""
    register_default_hooks()
    start_cron_scheduler()

    if config.agent_workdir:
        from pathlib import Path
        from vocamind.tools import builtin

        builtin.set_workdir(Path(config.agent_workdir))

    client = ToolCallingClient(
        model=config.resolved_agent_llm_model,
        api_url=config.resolved_agent_llm_api_url,
        api_key_env=config.resolved_agent_llm_api_key_env,
    )

    logger.info("Agent daemon 启动，模型=%s", config.resolved_agent_llm_model)
    runtime.status_registry.update_agent(idle=True)

    while not should_stop_agent(runtime.stop_event):
        _sync_status(runtime)
        if should_wait_for_task(True):
            try:
                task_msg = runtime.task_queue.dequeue(block=True, timeout=1.0)
            except queue.Empty:
                continue
        else:
            continue

        # agent_lock：预留 busy/idle 翻转；status_registry 为对外可观测的 idle 真相源
        runtime.agent_lock.clear()
        try:
            logger.info("Agent 开始处理任务 %s: %s", task_msg.task_id, task_msg.subject)
            summary = agent_loop_for_task(runtime, client, config, task_msg)
            logger.info("Agent 结束任务 %s: %s", task_msg.task_id, summary[:100])
        except Exception:
            logger.exception("Agent 处理任务失败 %s", task_msg.task_id)
            fail_task(task_msg.task_id, "Agent failed with error")
            runtime.task_queue.notify_complete(task_msg.task_id, "Agent failed with error", status="failed")
        finally:
            runtime.agent_lock.set()
            runtime.status_registry.update_agent(idle=True, current_task_id=None)
