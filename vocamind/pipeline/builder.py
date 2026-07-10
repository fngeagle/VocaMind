"""管道构建与启动入口。"""
from __future__ import annotations

import logging
from typing import Optional

from pathlib import Path

from vocamind.agent import build_agent_runtime, start_agent_runtime
from vocamind.common import PipelineConfig
from vocamind.common.handler import ThreadManager
from vocamind.pipeline.state import PipelineContext
from vocamind.pipeline.factories import create_gateway, create_tts, create_voice_llm
from vocamind.pipeline.notification import forward_task_notification
from vocamind.tasks.artifacts import get_artifact_registry
from vocamind.tasks.store import get_task_store
from vocamind.tools import builtin

logger = logging.getLogger(__name__)


def build_pipeline(config: PipelineConfig) -> ThreadManager:
    """根据配置构建完整管道（S2S + Agent daemon）并返回线程管理器。"""
    # 创建管道上下文
    ctx = PipelineContext.create()

    # 初始化任务存储
    if config.agent_tasks_dir:
        get_task_store(Path(config.agent_tasks_dir))

    workdir = Path(config.agent_workdir) if config.agent_workdir else builtin.WORKDIR
    get_artifact_registry().set_workdir(workdir)

    # 构建 Agent 运行时
    ctx.agent_runtime = build_agent_runtime(
        config,
        ctx.stop_event,
        ctx.task_queue,
        ctx.status_registry,
        ctx.outbound_queue,
    )

    # 设置任务通知处理器
    ctx.task_queue.set_notification_handler(
        lambda note: forward_task_notification(ctx, note)
    )

    # 启动 Agent 运行时
    start_agent_runtime(ctx.agent_runtime, config)

    # 创建处理程序
    # 文本回复模式：将 LLM 输出直接转发，不合成音频。
    # 语音回复模式：将 LLM 输出合成音频。
    # 网关：接收用户输入，并将其转发给处理程序。
    handlers = [
        create_tts(ctx, config),
        create_voice_llm(ctx, config),
        create_gateway(ctx, config),
    ]
    return ThreadManager(handlers)


def run_pipeline(config: PipelineConfig) -> None:
    """启动管道并阻塞直到中断。"""
    from vocamind.gateway.artifacts_http import ArtifactsHttpServer

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info(
        "VocaMind S2S 启动 | 回复模式=%s | 打断=%s | ws=%s:%s | http=%s:%s | voice=%s | agent=%s",
        config.reply_mode.value,
        config.enable_interruption,
        config.ws_host,
        config.ws_port,
        config.http_host,
        config.http_port,
        config.resolved_voice_llm_model,
        config.resolved_agent_llm_model,
    )
    manager = build_pipeline(config)
    stop_event = manager.handlers[0].stop_event
    ArtifactsHttpServer(config.http_host, config.http_port, stop_event).start()
    try:
        manager.start()
        manager.join()
    except KeyboardInterrupt:
        logger.info("正在关闭管道...")
        manager.stop()
