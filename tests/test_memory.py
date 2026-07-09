"""Memory 模块测试。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

from vocamind.memory.core_store import get_core_memory_store
from vocamind.memory.prompts import format_core_memory_block
from vocamind.memory.session_store import MAX_CONTEXT_CHARS, get_dialogue_session


def test_core_memory_crud(tmp_path: Path):
    store = get_core_memory_store("u1", tmp_path / "core")
    assert "Added" in store.add("preferred_name", "小明", "profile")
    assert store.update("preferred_name", "明明") == "Updated core memory: preferred_name"
    entries = store.list_entries()
    assert entries[0].value == "明明"
    block = store.format_for_prompt()
    assert "明明" in block
    assert "身份画像" in block
    assert store.delete("preferred_name") == "Deleted core memory: preferred_name"
    assert store.format_for_prompt() == ""


def test_core_memory_add_duplicate(tmp_path: Path):
    store = get_core_memory_store("u2", tmp_path / "core")
    store.add("tone", "简洁", "preference")
    result = store.add("tone", "啰嗦", "preference")
    assert "Error" in result


def test_dialogue_session_build_and_record(tmp_path: Path):
    session = get_dialogue_session("u3", tmp_path / "sessions")
    session.record_turn("你好", "你好呀")
    session.record_turn("写个作文", "已经交给后台了")
    messages = session.build_llm_messages("我们之前聊了什么")
    assert messages[0]["content"] == "你好"
    assert messages[-1]["content"] == "我们之前聊了什么"
    session.save()
    loaded = get_dialogue_session("u3", tmp_path / "sessions")
    assert len(loaded.turns) == 4


def test_dialogue_session_compact(tmp_path: Path):
    session = get_dialogue_session("u4", tmp_path / "sessions")
    for i in range(20):
        session.record_turn(f"用户问题{i} " + "x" * 400, f"助手回答{i} " + "y" * 400)
    assert session.estimate_chars() > MAX_CONTEXT_CHARS
    summarizer = MagicMock(return_value="用户多次提问，助手均已回应。")
    session.compact_if_needed(summarizer)
    assert session.summary
    assert session.estimate_chars() <= MAX_CONTEXT_CHARS
    summarizer.assert_called()


def test_format_core_memory_block_empty():
    assert format_core_memory_block([]) == ""
