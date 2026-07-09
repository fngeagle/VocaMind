"""OpenAI 兼容 API 的流式 LLM 实现，支持打断。"""
from __future__ import annotations

import logging
import os
import random
import time
from queue import Queue
from threading import Event
from typing import Dict, Iterator, Union

from openai import OpenAI

from vocamind.common.config import PipelineConfig
from vocamind.common.timing import log_elapsed
from vocamind.llm.base import LLMHandlerBase
from vocamind.llm.stream_conditions import (
    should_abort_stream,
    should_emit_interruption_transition,
)
from vocamind.llm.stream_state import LLMStreamState
from vocamind.llm.stream_steps import (
    append_stream_delta,
    build_chunk_output,
    extract_ready_sentences,
    extract_tail_sentence,
)

logger = logging.getLogger(__name__)


class OpenAILLMHandler(LLMHandlerBase):
    """通过 OpenAI 兼容接口流式调用大模型，按句 yield。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        interruption_event: Event,
        config: PipelineConfig,
    ) -> None:
        super().__init__(
            stop_event,
            cur_conn_end_event,
            queue_in,
            queue_out,
            interruption_event,
            chat_size=config.chat_size,
            system_prompt=config.system_prompt,
        )
        self.config = config
        self.transitions = config.interruption_transitions
        api_key = os.getenv(config.llm_api_key_env)
        if not api_key:
            raise ValueError(f"环境变量 {config.llm_api_key_env} 未设置")
        self.client = OpenAI(api_key=api_key, base_url=config.llm_api_url)

    def process(self, inputs: Dict[str, Union[str, int, bool]]) -> Iterator[Dict[str, Union[str, int, bool, None]]]:
        with self._inference_lock:
            yield from self._process_locked(inputs)

    def _process_locked(
        self, inputs: Dict[str, Union[str, int, bool]]
    ) -> Iterator[Dict[str, Union[str, int, bool, None]]]:
        prompt = inputs["data"]
        user_input_count = inputs["user_input_count"]
        uid = inputs["uid"]
        audio_input = inputs["audio_input"]

        if should_emit_interruption_transition(self.interruption_event):
            self.interruption_event.clear()
            time.sleep(0.3)
            transition = random.choice(self.transitions)
            yield build_chunk_output(
                question_text=prompt if audio_input else None,
                answer_text=transition,
                end_flag=False,
                user_input_count=user_input_count,
                uid=uid,
            )

        messages = self._append_user(prompt)
        logger.info("LLM 输入 messages 条数: %d", len(messages))

        total_start = time.perf_counter()
        stream_start = time.perf_counter()
        stream = self.client.chat.completions.create(
            model=self.config.llm_model,
            messages=messages,
            max_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
            stream=True,
        )
        log_elapsed("LLM 建立流式连接", stream_start, uid=uid, count=user_input_count)

        state = LLMStreamState()
        last_yield_start = total_start

        for chunk in stream:
            if should_abort_stream(self.interruption_event):
                logger.info("LLM 生成因打断而中止")
                break
            delta = chunk.choices[0].delta.content
            if not delta:
                continue
            if not state.first_token_logged:
                log_elapsed("LLM 首token", total_start, uid=uid, count=user_input_count)
                last_yield_start = time.perf_counter()
            state = append_stream_delta(state, delta)

            while not should_abort_stream(self.interruption_event):
                state, outputs = extract_ready_sentences(
                    state,
                    prompt=prompt,
                    audio_input=audio_input,
                    user_input_count=user_input_count,
                    uid=uid,
                )
                if not outputs:
                    break
                for output in outputs:
                    yield output
                    log_elapsed(
                        "LLM 产出句子",
                        last_yield_start,
                        seq=state.sentence_count,
                        text=output["answer_text"],
                        uid=uid,
                        count=user_input_count,
                    )
                    last_yield_start = time.perf_counter()

        if not should_abort_stream(self.interruption_event):
            state, tail = extract_tail_sentence(
                state,
                prompt=prompt,
                audio_input=audio_input,
                user_input_count=user_input_count,
                uid=uid,
            )
            if tail:
                yield tail
                log_elapsed(
                    "LLM 产出尾句",
                    last_yield_start,
                    seq=state.sentence_count,
                    text=tail["answer_text"],
                    uid=uid,
                    count=user_input_count,
                )

        if state.generated_text and not should_abort_stream(self.interruption_event):
            self._append_assistant(state.generated_text)

        log_elapsed(
            "LLM 推理总计",
            total_start,
            sentences=state.sentence_count,
            uid=uid,
            count=user_input_count,
        )
        logger.info("LLM 推理完成")
