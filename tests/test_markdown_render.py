"""Markdown 渲染测试（Node 不可直接跑，供手动验证逻辑）。"""
# 使用 Python 复刻关键规则做单元测试

import re


def is_horizontal_rule(line: str) -> bool:
    return bool(re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", line.strip()))


def is_table_separator(line: str) -> bool:
    trimmed = line.strip()
    if "|" not in trimmed and "-" not in trimmed:
        return False
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", trimmed))


def test_horizontal_rule():
    assert is_horizontal_rule("---")
    assert is_horizontal_rule("***")
    assert is_horizontal_rule("___")
    assert is_horizontal_rule("---  ")
    assert not is_horizontal_rule("- item")


def test_table_separator():
    assert is_table_separator("| --- | --- |")
    assert is_table_separator("|:---|:---:|")
    assert not is_table_separator("| cell | cell |")
