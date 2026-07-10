"""main.py CLI 与 pipeline wiring 测试。"""
from unittest.mock import patch

from vocamind.common import PipelineConfig, ReplyMode, TTSBackend
from vocamind.common.handler import ThreadManager
from vocamind.common.protocols import PipelineNode
from vocamind.pipeline import PipelineContext, build_pipeline
from vocamind.pipeline.factories import create_gateway, create_tts, create_voice_llm
from vocamind.tts import PassthroughTTSHandler
from vocamind.voice import VoiceOrchestratorHandler


def test_pipeline_context_queues():
    ctx = PipelineContext.create()
    assert ctx.text_prompt_queue is not None
    assert ctx.session is not None
    assert ctx.task_queue is not None
    assert ctx.status_registry is not None


def test_create_tts_passthrough_for_text_mode():
    ctx = PipelineContext.create()
    config = PipelineConfig(reply_mode=ReplyMode.TEXT, tts_backend=TTSBackend.API)
    tts = create_tts(ctx, config)
    assert isinstance(tts, PassthroughTTSHandler)


@patch.dict("os.environ", {"ASR_TTS_API_KEY": "test", "LLM_API_KEY": "test", "AGENT_LLM_API_KEY": "test"})
@patch("vocamind.pipeline.builder.start_agent_runtime")
@patch("vocamind.llm.tool_client.OpenAI")
def test_build_pipeline_all_nodes_implement_protocol(mock_openai, mock_start_agent):
    config = PipelineConfig(
        reply_mode=ReplyMode.TEXT,
        tts_backend=TTSBackend.NONE,
    )
    manager = build_pipeline(config)
    assert isinstance(manager, ThreadManager)
    mock_start_agent.assert_called_once()
    for node in manager.handlers:
        assert isinstance(node, PipelineNode)
    voice_handlers = [h for h in manager.handlers if isinstance(h, VoiceOrchestratorHandler)]
    assert len(voice_handlers) == 1


@patch.dict("os.environ", {"ASR_TTS_API_KEY": "test", "LLM_API_KEY": "test", "AGENT_LLM_API_KEY": "test"})
@patch("vocamind.llm.tool_client.OpenAI")
def test_factory_gateway_uses_context_queues(mock_openai):
    ctx = PipelineContext.create()
    from vocamind.agent import build_agent_runtime

    ctx.agent_runtime = build_agent_runtime(
        PipelineConfig(), ctx.stop_event, ctx.task_queue, ctx.status_registry
    )
    config = PipelineConfig()
    gateway = create_gateway(ctx, config)
    assert gateway.stop_event is ctx.stop_event
    voice = create_voice_llm(ctx, config)
    assert isinstance(voice, VoiceOrchestratorHandler)
    assert voice.queue_in is ctx.text_prompt_queue
