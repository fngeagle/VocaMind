"""Agent 能力说明：供 Voice LLM 了解后台可执行范围（只读，无执行逻辑）。"""
from __future__ import annotations

# 面向用户的口语化能力分组，与 tools/* 能力对齐
AGENT_CAPABILITY_GROUPS: list[tuple[str, list[str]]] = [
    (
        "信息检索",
        [
            "搜索互联网获取最新资讯（标题、链接、摘要）",
        ],
    ),
    (
        "文件与命令",
        [
            "运行 shell 命令（安装依赖、构建、测试、脚本等）",
            "读取、写入、编辑项目内文件",
            "按 glob 模式搜索文件",
        ],
    ),
    (
        "任务与进度",
        [
            "创建、认领、完成带依赖关系的持久化任务",
            "维护会话内 todo 清单",
            "长耗时命令可放后台执行，完成后通知",
        ],
    ),
    (
        "调度与自动化",
        [
            "注册 cron 定时任务（周期性或一次性提醒）",
            "查看、取消已注册的定时任务",
        ],
    ),
    (
        "协作与扩展",
        [
            "启动子 Agent 处理独立子问题并返回摘要",
            "spawn 自主队友、收发消息、计划审批与关停",
            "连接 MCP 服务（如 docs 文档搜索、deploy 部署查询）",
        ],
    ),
]

# 派发任务时的描述示例（教 Voice 模型如何写 subject/description）
DISPATCH_EXAMPLES: list[tuple[str, str]] = [
    ("运行项目测试", "在项目根目录执行 pytest，汇总失败用例"),
    ("整理依赖", "读取 requirements.txt，检查是否缺少 pytest"),
    ("查文档", "连接 docs MCP，搜索 VAD 配置相关说明"),
    ("定时提醒", "每天 9 点提醒我 standup（需 Agent 侧 schedule_cron）"),
]


def format_agent_capabilities_for_voice() -> str:
    """生成注入 Voice system prompt 的能力说明文本。"""
    lines = [
        "【后台 Agent 能做什么】",
        "以下工作由后台 Agent 执行，你无法直接操作，只能通过 dispatch_task 派发：",
    ]
    for title, items in AGENT_CAPABILITY_GROUPS:
        lines.append(f"- {title}：" + "；".join(items))
    lines.append("")
    lines.append("【你不能做的】直接 bash、读写文件、连 MCP、跑 cron——这些都要派发给 Agent。")
    lines.append("")
    lines.append("【dispatch_task 写法】")
    lines.append("- subject：简短标题（用户能听懂）")
    lines.append("- description：具体目标、约束、期望输出，越清楚越好")
    lines.append("示例：")
    for subject, desc in DISPATCH_EXAMPLES:
        lines.append(f"  - subject={subject!r} → description={desc!r}")
    lines.append("")
    lines.append("【你的工具】")
    lines.append("- dispatch_task：用户明确要求做事时派发")
    lines.append("- list_tasks / get_task：查任务列表或详情")
    lines.append("- query_status：查 Agent、后台任务、cron、队友、MCP 等全局状态")
    return "\n".join(lines)
