"""Voice Orchestrator Handler：S2S 管道中的 Voice LLM 节点。"""
from __future__ import annotations

import logging
import os
import random
import time
from queue import Queue
from threading import Event
from typing import Dict, Iterator, Union

from vocamind.agent.state import AgentRuntime
from vocamind.common.config import PipelineConfig
from vocamind.common.handler import BaseHandler
from vocamind.llm.stream_conditions import should_emit_interruption_transition
from vocamind.llm.stream_steps import build_chunk_output
from vocamind.llm.tool_client import ToolCallingClient
from vocamind.memory import get_dialogue_session
from vocamind.status import StatusRegistry
from vocamind.voice.steps import run_voice_turn

logger = logging.getLogger(__name__)


class VoiceOrchestratorHandler(BaseHandler):
    """Voice LLM：对话 + 派发任务 + 查询状态，不执行 Agent 工具。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        interruption_event: Event,
        assistant_turn_active: Event,
        agent_runtime: AgentRuntime,
        status_registry: StatusRegistry,
        config: PipelineConfig,
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out)
        self.interruption_event = interruption_event
        self.assistant_turn_active = assistant_turn_active
        self.agent_runtime = agent_runtime
        self.status_registry = status_registry
        self.config = config
        api_key = os.getenv(config.resolved_voice_llm_api_key_env)
        if not api_key:
            raise ValueError(f"环境变量 {config.resolved_voice_llm_api_key_env} 未设置")
        self.client = ToolCallingClient(
            model=config.resolved_voice_llm_model,
            api_url=config.resolved_voice_llm_api_url,
            api_key_env=config.resolved_voice_llm_api_key_env,
        )

    def process(self, inputs: Dict[str, Union[str, int, bool]]) -> Iterator[Dict[str, Union[str, int, bool, None]]]:
        prompt = str(inputs["data"])
        user_input_count = int(inputs["user_input_count"])
        uid = inputs.get("uid")
        audio_input = bool(inputs.get("audio_input"))
        proactive = bool(inputs.get("proactive"))

        self.assistant_turn_active.set()
        try:
            if should_emit_interruption_transition(self.interruption_event) and not proactive:
                self.interruption_event.clear()
                time.sleep(0.3)
                transition = random.choice(self.config.interruption_transitions)
                yield build_chunk_output(
                    question_text=prompt if audio_input else None,
                    answer_text=transition,
                    end_flag=False,
                    user_input_count=user_input_count,
                    uid=uid,
                    proactive=proactive,
                )

            dialogue_session = get_dialogue_session(str(uid) if uid else None)
            yield from run_voice_turn(
                self.client,
                self.agent_runtime,
                self.status_registry,
                self.config,
                prompt,
                user_input_count,
                uid,
                audio_input,
                self.interruption_event,
                dialogue_session,
                proactive=proactive,
            )
        finally:
            self.assistant_turn_active.clear()
