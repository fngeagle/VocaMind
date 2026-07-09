"""Agent Loop 终止与分支条件。"""
from __future__ import annotations

from threading import Event

from vocamind.agent.state import AgentContext
from vocamind.llm.tool_client import RecoveryState, has_tool_calls, is_prompt_too_long_error


CONTINUATION_PROMPT = "Continue from the previous response. Do not repeat completed work."
DEFAULT_MAX_TOKENS = 4096
ESCALATED_MAX_TOKENS = 8192
MAX_RECOVERY_RETRIES = 2


def should_stop_agent(stop_event: Event) -> bool:
    return stop_event.is_set()


def should_wait_for_task(idle: bool) -> bool:
    return idle


def should_continue_agent_cycle(ctx: AgentContext, assistant_message: object) -> bool:
    return has_tool_calls(assistant_message)


def should_handle_max_tokens(recovery: RecoveryState, max_tokens: int) -> tuple[bool, int]:
    if not recovery.has_escalated:
        recovery.has_escalated = True
        return True, ESCALATED_MAX_TOKENS
    if recovery.recovery_count < MAX_RECOVERY_RETRIES:
        recovery.recovery_count += 1
        return True, max_tokens
    return False, max_tokens


def should_reactive_compact(exc: Exception, recovery: RecoveryState) -> bool:
    return is_prompt_too_long_error(exc) and not recovery.has_attempted_reactive_compact


def should_run_background_tool(tool_name: str, tool_input: dict) -> bool:
    from vocamind.tools.background import should_run_background

    return should_run_background(tool_name, tool_input)
