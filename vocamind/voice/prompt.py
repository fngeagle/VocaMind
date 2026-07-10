"""Voice LLM system prompt 组装。"""
from __future__ import annotations

from datetime import datetime

from vocamind.memory import get_core_memory_store
from vocamind.memory.prompts import CORE_MEMORY_TOOL_GUIDANCE
from vocamind.tools.capabilities import format_agent_capabilities_for_voice

_WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")


def format_voice_runtime_context() -> str:
    """注入 Voice 可直接使用的环境信息（时间等）。"""
    now = datetime.now()
    weekday = _WEEKDAY_CN[now.weekday()]
    return (
        f"【当前环境】\n"
        f"- 本地时间：{now.strftime('%Y年%m月%d日 %H:%M:%S')}，星期{weekday}"
    )


def format_voice_behavior_rules() -> str:
    """工具调用决策规则与正反例（模型自行判断，无代码层关键词门控）。"""
    return """【默认行为】
每轮优先结合对话历史与 Core Memory 直接用口语回复用户，不调用任何工具。

【仅以下情况可调用工具】
- dispatch_task：用户明确要求你去「做」某件需要后台执行的事（跑命令、读写文件、构建测试等）
- query_status：用户问系统/Agent/后台任务/cron 等整体状态
- list_tasks / get_task：用户明确要列任务或查某个 task_id
- core_memory_add / update / delete：用户透露或修正长期稳定的个人信息（见 Core Memory 工具说明）

【禁止调用工具的情况】
- 问候、寒暄、感谢、道别、闲聊（除非同时透露需写入 Core Memory 的稳定信息）
- 问当前时间/日期/星期（用【当前环境】直接回答）
- 解释、观点、一般知识问答
- 用户问「之前说了什么」「我们聊过什么」——直接根据对话摘要与历史回答，禁止声称「第一次聊天」

【调用工具后怎么说话】
- dispatch_task 后：只说「已经提交给后台处理了，好了会通知你」，绝不说「写好了」「完成了」
- query_status / list_tasks 后：用纯口语短句概括；优先说最近相关任务；状态用待处理/进行中/已完成/失败
- core_memory 变更后：简短确认即可，勿朗读 key/value
- 收到 [TaskFailed] 通知：如实说任务没做成，不要谎称完成
- 收到 [TaskDone] 通知：冒号后是后台交付摘要，用口语把其中的关键事实告诉用户，才可说任务完成了
- 若同时收到 attachments 文档卡片：告知用户「报告已在界面上，你可以点开看」
- 若摘要里提到「完整文档已写入」或「节选」：先播报节选要点，再说明完整文档可在界面查看
- 禁止说「看不到具体结果」「没有收到内容」——摘要里有的信息必须念出来
- 禁止 markdown（不要用加粗、列表符号），语音播报用口语

【任务状态含义】
- 待处理：刚派发，Agent 还没真正开始
- 进行中：Agent 正在执行
- 已完成：后台确实做完了
- 失败：执行出错（如 API 失败），工作没完成

【正反例】
用户：你好 → 直接说「你好呀，有什么可以帮你？」（不调工具）
用户：几点了 → 用【当前环境】时间直接回答（不调工具）
用户：我们之前聊了什么 → 根据对话摘要/历史概括，禁止说「第一次聊天」
用户：以后叫我小明 → core_memory_add 后口语确认
用户：任务咋样了 → 调 list_tasks，口语说最新任务状态
用户：帮我写个报告 → dispatch_task 后说「好，已经交给后台写了，好了告诉你」"""


def assemble_voice_system_prompt(base_prompt: str, uid: str | None = None) -> str:
    """组装完整 Voice system prompt，含 Core Memory 动态注入。"""
    parts = [base_prompt.strip()]
    if uid:
        core_block = get_core_memory_store(uid).format_for_prompt()
        if core_block:
            parts.append(core_block)
    parts.extend(
        [
            format_voice_runtime_context(),
            CORE_MEMORY_TOOL_GUIDANCE,
            format_voice_behavior_rules(),
            format_agent_capabilities_for_voice(),
        ]
    )
    return "\n\n".join(parts)
