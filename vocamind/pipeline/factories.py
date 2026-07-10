"""管道节点工厂：按配置实例化 Voice LLM / TTS / Gateway。"""
from __future__ import annotations

from vocamind.common import PipelineConfig, ReplyMode, TTSBackend
from vocamind.common.handler import BaseHandler
from vocamind.gateway import WebSocketGateway
from vocamind.pipeline.state import PipelineContext
from vocamind.tts import APITTSHandler, PassthroughTTSHandler
from vocamind.voice import VoiceOrchestratorHandler


def create_voice_llm(ctx: PipelineContext, config: PipelineConfig) -> BaseHandler:
    if ctx.agent_runtime is None:
        raise ValueError("PipelineContext.agent_runtime 未初始化")
    return VoiceOrchestratorHandler(
        ctx.stop_event,
        ctx.cur_conn_end_event,
        queue_in=ctx.text_prompt_queue,
        queue_out=ctx.lm_response_queue,
        interruption_event=ctx.interruption_event,
        assistant_turn_active=ctx.assistant_turn_active,
        agent_runtime=ctx.agent_runtime,
        status_registry=ctx.status_registry,
        config=config,
    )


def create_llm(ctx: PipelineContext, config: PipelineConfig) -> BaseHandler:
    """兼容别名：S2S 路径使用 VoiceOrchestratorHandler。"""
    return create_voice_llm(ctx, config)


def create_tts(ctx: PipelineContext, config: PipelineConfig) -> BaseHandler:
    if config.reply_mode == ReplyMode.TEXT or config.tts_backend == TTSBackend.NONE:
        return PassthroughTTSHandler(
            ctx.stop_event,
            ctx.cur_conn_end_event,
            queue_in=ctx.lm_response_queue,
            queue_out=ctx.outbound_queue,
            should_listen=ctx.should_listen,
            pending_attachments=ctx.pending_attachments,
        )
    if config.tts_backend != TTSBackend.API:
        raise ValueError(f"不支持的 TTS 后端: {config.tts_backend}")
    return APITTSHandler(
        ctx.stop_event,
        ctx.cur_conn_end_event,
        queue_in=ctx.lm_response_queue,
        queue_out=ctx.outbound_queue,
        should_listen=ctx.should_listen,
        interruption_event=ctx.interruption_event,
        config=config,
        pending_attachments=ctx.pending_attachments,
    )


def create_gateway(ctx: PipelineContext, config: PipelineConfig) -> WebSocketGateway:
    return WebSocketGateway(
        stop_event=ctx.stop_event,
        should_listen=ctx.should_listen,
        interruption_event=ctx.interruption_event,
        assistant_turn_active=ctx.assistant_turn_active,
        session_lifecycle=ctx.session,
        text_prompt_queue=ctx.text_prompt_queue,
        lm_response_queue=ctx.lm_response_queue,
        outbound_queue=ctx.outbound_queue,
        config=config,
    )
