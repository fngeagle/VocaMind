"""Agent 任务完成后，构建可播报给 Voice 的交付摘要。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from vocamind.llm.tool_client import parse_tool_arguments

# Voice 主动通知的可播报长度上限
MAX_VOICE_SUMMARY_CHARS = 1200
# 文档节选长度
DOC_EXCERPT_CHARS = 400

# 无实质内容的「空话」摘要特征
_HOLLOW_PATTERNS = (
    "以上即为",
    "完整查询结果",
    "任务已完成",
    "任务完成",
    "已完成",
    "查询完毕",
    "Task completed",
    "以上是",
    "具体如下",
    "如下所示",
)

# 优先纳入摘要的工具输出
_PRIORITY_TOOLS = ("web_search", "read_file", "bash")


def _is_hollow_summary(text: str) -> bool:
    """判断摘要是否只有元描述、缺少可播报事实。"""
    stripped = text.strip()
    if not stripped:
        return True
    if any(p in stripped for p in _HOLLOW_PATTERNS):
        return len(stripped) < 120
    return False


def _last_assistant_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = (msg.get("content") or "").strip()
            if content:
                return content
    return ""


def _tool_name_by_id(messages: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            mapping[tc.get("id", "")] = fn.get("name", "")
    return mapping


def _collect_tool_outputs(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """返回 (tool_name, content) 列表，按出现顺序。"""
    name_map = _tool_name_by_id(messages)
    outputs: list[tuple[str, str]] = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "").strip()
        if not content or content.startswith("Error:"):
            continue
        tool_id = msg.get("tool_call_id", "")
        tool_name = name_map.get(tool_id, "")
        outputs.append((tool_name, content))
    return outputs


def _collect_write_paths(messages: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name") != "write_file":
                continue
            try:
                args = parse_tool_arguments(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            path = str(args.get("path") or "").strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def _read_doc_excerpt(path: str, workdir: Path | None) -> str:
    if not workdir:
        return ""
    try:
        from vocamind.tools.builtin import safe_path

        fp = safe_path(path, workdir)
        if not fp.is_file():
            return ""
        text = fp.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return ""
        if len(text) <= DOC_EXCERPT_CHARS:
            return text
        return text[:DOC_EXCERPT_CHARS].rstrip() + "…"
    except Exception:
        return ""


def _summarize_from_tools(outputs: list[tuple[str, str]]) -> str:
    """从工具输出中提取可播报内容。"""
    if not outputs:
        return ""

    def _usable(name: str, content: str) -> bool:
        if name == "write_file" or content.startswith("Wrote ") and " bytes to " in content:
            return False
        return bool(content) and not content.startswith("Error")

    usable = [(n, c) for n, c in outputs if _usable(n, c)]
    if not usable:
        return ""

    for name, content in reversed(usable):
        if name == "web_search":
            return _trim_search_output(content)

    last = usable[-1][1]
    if len(last) > 600:
        return last[:600].rstrip() + "…"
    return last


def _trim_search_output(content: str) -> str:
    """压缩 web_search 格式化输出，保留前几条结果。"""
    if len(content) <= 900:
        return content
    lines = [ln for ln in content.splitlines() if ln.strip()]
    kept: list[str] = []
    total = 0
    for ln in lines:
        if total + len(ln) > 850 and kept:
            break
        kept.append(ln)
        total += len(ln) + 1
    text = "\n".join(kept).strip()
    return text + "…"


def build_voice_delivery_summary(
    messages: list[dict[str, Any]],
    *,
    workdir: Path | None = None,
    max_chars: int = MAX_VOICE_SUMMARY_CHARS,
) -> str:
    """
    构建 Agent → Voice 的交付摘要。

    - 优先使用 Agent 最终回复中的事实性内容
    - 若为空话，则从 web_search / read_file 等工具输出回填
    - 若写了文档，附带路径与节选，并说明还有完整文档
    """
    tool_outputs = _collect_tool_outputs(messages)
    assistant_text = _last_assistant_text(messages)

    main = assistant_text if assistant_text and not _is_hollow_summary(assistant_text) else ""
    if not main:
        main = _summarize_from_tools(tool_outputs)

    parts: list[str] = []
    if main:
        parts.append(main.strip())

    for rel_path in _collect_write_paths(messages):
        excerpt = _read_doc_excerpt(rel_path, workdir)
        if excerpt:
            parts.append(f"完整文档已写入 {rel_path}，以下是节选：{excerpt}")
        else:
            parts.append(f"完整文档已写入 {rel_path}，可在界面点击查看。")

    if not parts:
        return "任务已完成，但未提取到可播报的具体结果。"

    summary = "\n\n".join(parts)
    summary = re.sub(r"\n{3,}", "\n\n", summary).strip()
    if len(summary) > max_chars:
        return summary[: max_chars - 1].rstrip() + "…"
    return summary
