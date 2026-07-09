"""Memory 模块提示词。"""
from __future__ import annotations

from vocamind.memory.core_store import CoreMemoryEntry

_CATEGORY_CN = {
    "profile": "身份画像",
    "habit": "行为习惯",
    "preference": "偏好取向",
    "constraint": "沟通约束",
}


def format_core_memory_block(entries: list[CoreMemoryEntry]) -> str:
    """将 Core Memory 条目格式化为 system prompt 注入块。"""
    if not entries:
        return ""
    lines = [
        "【Core Memory · 用户长期画像】",
        "以下为用户跨会话沉淀的稳定信息（身份、偏好、习惯、沟通约束）。",
        "使用原则：",
        "1. 自然融入回答，勿逐条复读或刻意声明「我记得你…」",
        "2. 与当前发言冲突时以当前发言为准，并调用 core_memory_update 修正条目",
        "3. 禁止臆造未列出的用户属性",
        "",
        "条目：",
    ]
    for entry in sorted(entries, key=lambda e: e.key):
        cat = _CATEGORY_CN.get(entry.category, entry.category)
        lines.append(f"- [{cat}] {entry.key}：{entry.value}")
    return "\n".join(lines)


CORE_MEMORY_TOOL_GUIDANCE = """【Core Memory 工具 · 增删改】
当用户透露**跨会话仍成立**的稳定信息时，维护 Core Memory（查不需调工具，系统已注入）：
- core_memory_add：写入新条目（key 用简短 snake_case，value 用中文描述）
- core_memory_update：修正或补充已有 key
- core_memory_delete：用户明确要求删除/忘记某条目

适用：称呼、身份、写作/回复偏好、常用指令风格、禁忌话题、长期目标
不适用：一次性任务、临时情绪、本轮会话内的事实（由对话摘要覆盖）

category：profile | habit | preference | constraint"""


DIALOGUE_SUMMARY_PROMPT = """请将以下对话内容压缩为简洁的中文摘要，供后续对话延续上下文。
要求：
1. 保留用户核心诉求、已做决策、已派发任务及结论、重要事实与约束
2. 省略寒暄、重复与无信息量的来回
3. 使用第三人称客观叙述，300–600 字以内
4. 若存在「已有摘要」，将其与新内容合并为一份完整摘要，不要输出两份"""
