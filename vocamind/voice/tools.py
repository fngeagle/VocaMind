"""Voice LLM 有限工具：派发任务、查询状态、Core Memory 维护。"""
from __future__ import annotations

from typing import Any, Callable

from vocamind.agent.state import AgentRuntime
from vocamind.memory import get_core_memory_store
from vocamind.status import StatusRegistry, query_all_status
from vocamind.tasks import create_task, get_task_json, list_tasks_summary
from vocamind.tasks.queue import AgentTaskMessage

VOICE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "dispatch_task",
        "description": (
            "仅当用户明确要求执行需要后台 Agent 完成的工作时调用（如跑测试、读写文件、安装依赖）。"
            "问候、闲聊、问时间/日期、一般问答时禁止调用。"
            "subject 为简短标题，description 为具体目标与期望输出。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "blockedBy": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["subject"],
        },
    },
    {
        "name": "list_tasks",
        "description": "仅当用户明确要查看任务列表时调用。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_task",
        "description": "仅当用户提供了 task_id 或明确要查某个任务详情时调用。",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "query_status",
        "description": (
            "仅当用户明确询问系统状态、Agent 进度、后台任务、cron、队友或 MCP 连接时调用。"
            "问候或简单闲聊时不要调用。"
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "core_memory_add",
        "description": (
            "写入用户长期稳定信息（跨会话有效）。"
            "适用于称呼、身份、偏好、习惯、沟通约束。"
            "key 用 snake_case；若 key 已存在应改用 core_memory_update。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["profile", "habit", "preference", "constraint"],
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "core_memory_update",
        "description": "更新已有 Core Memory 条目。",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["profile", "habit", "preference", "constraint"],
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "core_memory_delete",
        "description": "删除 Core Memory 条目（用户明确要求忘记时）。",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
]


def build_voice_handlers(
    runtime: AgentRuntime,
    status_registry: StatusRegistry,
    user_input_count: int = 0,
    uid: str | None = None,
) -> dict[str, Callable[..., str]]:
    memory = get_core_memory_store(uid)

    def dispatch_task(subject: str, description: str = "", blockedBy: list[str] | None = None) -> str:
        task = create_task(subject, description, blockedBy)
        runtime.task_queue.enqueue(
            AgentTaskMessage(
                task_id=task.id,
                subject=task.subject,
                description=task.description or description,
                source="voice",
                user_input_count=user_input_count,
                uid=uid,
            )
        )
        status_registry.set_queue_pending(runtime.task_queue.pending_count)
        return f"Dispatched {task.id}: {task.subject} (status=pending, agent will process)"

    def _list_tasks() -> str:
        return list_tasks_summary()

    def _get_task(task_id: str) -> str:
        try:
            return get_task_json(task_id)
        except FileNotFoundError:
            return f"Error: task {task_id} not found"

    def _query_status() -> str:
        return query_all_status(status_registry)

    def core_memory_add(key: str, value: str, category: str = "profile") -> str:
        return memory.add(key, value, category)

    def core_memory_update(key: str, value: str, category: str | None = None) -> str:
        return memory.update(key, value, category)

    def core_memory_delete(key: str) -> str:
        return memory.delete(key)

    return {
        "dispatch_task": dispatch_task,
        "list_tasks": _list_tasks,
        "get_task": _get_task,
        "query_status": _query_status,
        "core_memory_add": core_memory_add,
        "core_memory_update": core_memory_update,
        "core_memory_delete": core_memory_delete,
    }
