"""工具事件消息测试。"""
from vocamind.common.tool_events import (
    build_tool_end,
    build_tool_start,
    is_tool_event,
    preview_tool_content,
)


def test_is_tool_event():
    assert is_tool_event({"type": "tool_event", "event": "start"})
    assert not is_tool_event({"answer_text": "hi"})


def test_build_tool_start_end():
    start = build_tool_start(
        tool_call_id="c1",
        tool_name="web_search",
        arguments={"query": "test"},
        scope="voice",
        uid="u1",
        user_input_count=2,
    )
    assert start["event"] == "start"
    assert start["tool_name"] == "web_search"

    end = build_tool_end(
        tool_call_id="c1",
        tool_name="web_search",
        status="success",
        content="ok",
        scope="voice",
        uid="u1",
        user_input_count=2,
    )
    assert end["event"] == "end"
    assert end["content_preview"] == "ok"


def test_preview_truncates():
    long_text = "x" * 1000
    preview = preview_tool_content(long_text, limit=100)
    assert len(preview) > 100
    assert "1000" in preview
