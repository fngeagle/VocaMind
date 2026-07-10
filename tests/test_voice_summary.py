"""Agent → Voice 交付摘要测试。"""
from pathlib import Path

from vocamind.agent.voice_summary import build_voice_delivery_summary


def test_uses_assistant_text_when_substantive():
    messages = [
        {"role": "user", "content": "Task: search"},
        {"role": "assistant", "content": "今日发射 3 次：长征五号、快舟一号、谷神星一号。"},
    ]
    summary = build_voice_delivery_summary(messages)
    assert "长征五号" in summary
    assert "3 次" in summary


def test_falls_back_to_web_search_when_assistant_hollow():
    search_out = (
        "Search (duckduckgo): 中国火箭发射\n"
        "Results: 2\n\n"
        "1. 长征五号成功发射\n"
        "   URL: https://example.com/a\n"
        "   今日在文昌发射\n"
    )
    messages = [
        {"role": "user", "content": "Task: search"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "tc1",
                    "function": {"name": "web_search", "arguments": '{"query":"中国火箭发射"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc1", "content": search_out},
        {"role": "assistant", "content": "以上即为今日中国火箭发射情况的完整查询结果。"},
    ]
    summary = build_voice_delivery_summary(messages)
    assert "长征五号" in summary
    assert "以上即为" not in summary


def test_includes_document_excerpt(tmp_path: Path):
    doc_path = tmp_path / "report.md"
    doc_path.write_text("第一章：概述\n" + "详细内容。" * 80, encoding="utf-8")
    rel = "report.md"
    messages = [
        {"role": "user", "content": "Task: write report"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "tc2",
                    "function": {
                        "name": "write_file",
                        "arguments": f'{{"path":"{rel}","content":"ignored"}}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc2", "content": f"Wrote 100 bytes to {rel}"},
        {"role": "assistant", "content": "报告已写好。"},
    ]
    summary = build_voice_delivery_summary(messages, workdir=tmp_path)
    assert "完整文档已写入 report.md" in summary
    assert "第一章" in summary
    assert "界面点击查看" in summary or "报告已写好" in summary


def test_empty_messages_get_fallback():
    summary = build_voice_delivery_summary([])
    assert "未提取到可播报" in summary
