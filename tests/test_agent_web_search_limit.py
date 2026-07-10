"""Agent web_search 次数上限测试。"""
from unittest.mock import MagicMock

from vocamind.agent.conditions import MAX_WEB_SEARCH_PER_TASK
from vocamind.agent.state import AgentContext
from vocamind.agent.steps import execute_tool_batch


def _web_search_assistant() -> MagicMock:
    assistant = MagicMock()
    tc = MagicMock()
    tc.id = "tc_search"
    tc.function.name = "web_search"
    tc.function.arguments = '{"query":"test"}'
    assistant.tool_calls = [tc]
    return assistant


def test_web_search_runs_under_limit():
    ctx = AgentContext()
    calls: list[str] = []

    def _search(**kwargs):
        calls.append(kwargs.get("query", ""))
        return "Search results"

    results = execute_tool_batch(ctx, _web_search_assistant(), {"web_search": _search})
    assert len(calls) == 1
    assert ctx.web_search_count == 1
    assert results[0]["content"] == "Search results"


def test_web_search_blocked_at_limit():
    ctx = AgentContext(web_search_count=MAX_WEB_SEARCH_PER_TASK)

    def _search(**kwargs):
        raise AssertionError("should not be called")

    results = execute_tool_batch(ctx, _web_search_assistant(), {"web_search": _search})
    assert "上限" in results[0]["content"]
    assert str(MAX_WEB_SEARCH_PER_TASK) in results[0]["content"]
    assert ctx.web_search_count == MAX_WEB_SEARCH_PER_TASK
