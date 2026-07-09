"""Teammate 多 Agent 通信。"""
from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from vocamind.common.paths import PROJECT_ROOT
from vocamind.llm.tool_client import ToolCallingClient, get_tool_calls, has_tool_calls, parse_tool_arguments
from vocamind.tasks import claim_task, complete_task, get_task_json, list_tasks
from vocamind.tools.builtin import run_bash, run_read, run_write
from vocamind.tools.hooks import call_tool_handler

MAILBOX_DIR = PROJECT_ROOT / ".mailboxes"
MAILBOX_DIR.mkdir(parents=True, exist_ok=True)

active_teammates: dict[str, bool] = {}


class MessageBus:
    def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        msg_type: str = "message",
        metadata: dict | None = None,
    ) -> None:
        msg = {
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "type": msg_type,
            "ts": time.time(),
            "metadata": metadata or {},
        }
        inbox = MAILBOX_DIR / f"{to_agent}.jsonl"
        with inbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg) + "\n")

    def read_inbox(self, agent: str) -> list[dict[str, Any]]:
        inbox = MAILBOX_DIR / f"{agent}.jsonl"
        if not inbox.exists():
            return []
        msgs = [json.loads(line) for line in inbox.read_text(encoding="utf-8").splitlines() if line.strip()]
        inbox.unlink(missing_ok=True)
        return msgs


BUS = MessageBus()


@dataclass
class ProtocolState:
    request_id: str
    type: str
    sender: str
    target: str
    status: str
    payload: str
    created_at: float = field(default_factory=time.time)


pending_requests: dict[str, ProtocolState] = {}


def new_request_id() -> str:
    return f"req_{random.randint(0, 999999):06d}"


def match_response(response_type: str, request_id: str, approve: bool) -> None:
    state = pending_requests.get(request_id)
    if not state:
        return
    if state.type == "shutdown" and response_type != "shutdown_response":
        return
    if state.type == "plan_approval" and response_type != "plan_approval_response":
        return
    state.status = "approved" if approve else "rejected"


def consume_lead_inbox(route_protocol: bool = True) -> list[dict[str, Any]]:
    msgs = BUS.read_inbox("lead")
    if route_protocol:
        for msg in msgs:
            meta = msg.get("metadata", {})
            req_id = meta.get("request_id", "")
            msg_type = msg.get("type", "")
            if req_id and msg_type.endswith("_response"):
                match_response(msg_type, req_id, meta.get("approve", False))
    return msgs


def run_send_message(to: str, content: str) -> str:
    BUS.send("lead", to, content)
    return f"Sent to {to}"


def run_check_inbox() -> str:
    msgs = consume_lead_inbox(route_protocol=True)
    if not msgs:
        return "(inbox empty)"
    lines = []
    for m in msgs:
        meta = m.get("metadata", {})
        req_id = meta.get("request_id", "")
        tag = f" [{m['type']} req:{req_id}]" if req_id else f" [{m['type']}]"
        lines.append(f"  [{m['from']}]{tag} {m['content'][:200]}")
    return "\n".join(lines)


def run_request_shutdown(teammate: str) -> str:
    req_id = new_request_id()
    pending_requests[req_id] = ProtocolState(
        request_id=req_id, type="shutdown", sender="lead", target=teammate, status="pending", payload=""
    )
    BUS.send("lead", teammate, "Shut down.", "shutdown_request", {"request_id": req_id})
    return f"Shutdown request sent to {teammate}"


def run_request_plan(teammate: str, task: str) -> str:
    BUS.send("lead", teammate, f"Submit plan for: {task}", "message")
    return f"Asked {teammate} to submit a plan"


def run_review_plan(request_id: str, approve: bool, feedback: str = "") -> str:
    state = pending_requests.get(request_id)
    if not state:
        return f"Request {request_id} not found"
    state.status = "approved" if approve else "rejected"
    BUS.send(
        "lead",
        state.sender,
        feedback or ("Approved" if approve else "Rejected"),
        "plan_approval_response",
        {"request_id": request_id, "approve": approve},
    )
    return f"Plan {'approved' if approve else 'rejected'} for {state.sender}"


def _teammate_submit_plan(from_name: str, plan: str) -> str:
    req_id = new_request_id()
    pending_requests[req_id] = ProtocolState(
        request_id=req_id, type="plan_approval", sender=from_name, target="lead", status="pending", payload=plan
    )
    BUS.send(from_name, "lead", plan, "plan_approval_request", {"request_id": req_id})
    return f"Plan submitted ({req_id})"


def spawn_teammate_thread(
    name: str,
    role: str,
    prompt: str,
    client_factory: Callable[[], ToolCallingClient],
) -> str:
    if name in active_teammates:
        return f"Teammate '{name}' already exists"

    def run() -> None:
        client = client_factory()
        system = f"You are '{name}', a {role}. Use tools to complete tasks."
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        sub_tools = [
            {"name": "bash", "description": "Run shell.", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "list_tasks", "description": "List tasks.", "input_schema": {"type": "object", "properties": {}, "required": []}},
            {"name": "claim_task", "description": "Claim task.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
            {"name": "complete_task", "description": "Complete task.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}},
        ]
        sub_handlers = {
            "bash": run_bash,
            "read_file": run_read,
            "write_file": run_write,
            "list_tasks": lambda: "\n".join(f"  {t.id}: {t.subject} [{t.status}]" for t in list_tasks()) or "No tasks.",
            "claim_task": lambda task_id: claim_task(task_id, owner=name),
            "complete_task": complete_task,
        }
        for _ in range(20):
            inbox = BUS.read_inbox(name)
            for msg in inbox:
                if msg.get("type") == "shutdown_request":
                    active_teammates.pop(name, None)
                    return
                messages.append({"role": "user", "content": json.dumps(msg)})
            response = client.create(messages=messages[-20:], tools=sub_tools, system_prompt=system, max_tokens=4000)
            assistant = response.choices[0].message
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": assistant.content or ""}
            if assistant.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in assistant.tool_calls
                ]
            messages.append(assistant_msg)
            if not has_tool_calls(assistant):
                break
            for tc in get_tool_calls(assistant):
                tname = tc.function.name
                args = parse_tool_arguments(tc.function.arguments)
                if tname == "submit_plan":
                    output = _teammate_submit_plan(name, args.get("plan", ""))
                else:
                    handler = sub_handlers.get(tname)
                    output = call_tool_handler(handler, args, tname)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(output)})
        summary = messages[-1].get("content", "Done.") if messages else "Done."
        BUS.send(name, "lead", str(summary), "result")
        active_teammates.pop(name, None)

    active_teammates[name] = True
    threading.Thread(target=run, daemon=True).start()
    return f"Teammate '{name}' spawned as {role}"


def run_spawn_teammate(name: str, role: str, prompt: str, client_factory: Callable[[], ToolCallingClient]) -> str:
    return spawn_teammate_thread(name, role, prompt, client_factory)


def list_teammate_names() -> list[str]:
    return list(active_teammates.keys())
