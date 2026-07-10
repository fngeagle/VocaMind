"""Voice LLM 单步逻辑。"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterator

from vocamind.agent.state import AgentRuntime
from vocamind.common.config import PipelineConfig
from vocamind.common.tool_events import build_tool_end, build_tool_start
from vocamind.common.conversation_log import build_voice_record, now_iso, save_voice_turn
from vocamind.memory.session_store import DialogueSession
from vocamind.llm.stream_conditions import should_abort_stream
from vocamind.llm.stream_state import LLMStreamState
from vocamind.llm.stream_steps import (
    append_stream_delta,
    build_chunk_output,
    extract_ready_sentences,
    extract_tail_sentence,
)
from vocamind.llm.tool_client import ToolCallingClient, get_tool_calls, message_text, parse_tool_arguments
from vocamind.status import StatusRegistry
from vocamind.tools.hooks import call_tool_handler
from vocamind.voice.prompt import assemble_voice_system_prompt
from vocamind.voice.state import VoiceTurnState
from vocamind.voice.tools import VOICE_TOOLS, build_voice_handlers

logger = logging.getLogger(__name__)


def sanitize_speech_text(text: str) -> str:
    """去掉 markdown 等不适合 TTS 的格式。"""
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    cleaned = re.sub(r"^[\s]*[-*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{2,}", "。", cleaned)
    cleaned = cleaned.replace("\n", "，")
    return cleaned.strip()


def inject_voice_notifications(messages: list[dict[str, Any]], runtime: AgentRuntime) -> None:
    notes = runtime.task_queue.format_notifications_for_voice()
    for note in notes:
        messages.append({"role": "user", "content": note})


def call_voice_llm(
    client: ToolCallingClient,
    state: VoiceTurnState,
    config: PipelineConfig,
) -> Any:
    return client.create(
        messages=state.messages,
        tools=VOICE_TOOLS,
        system_prompt=assemble_voice_system_prompt(config.resolved_voice_system_prompt, state.uid),
        max_tokens=config.max_new_tokens,
        temperature=config.temperature,
    )


def append_voice_assistant(messages: list[dict[str, Any]], assistant_message: Any) -> None:
    msg: dict[str, Any] = {"role": "assistant", "content": assistant_message.content or ""}
    if assistant_message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in assistant_message.tool_calls
        ]
    messages.append(msg)


def append_tool_synthesis_nudge(messages: list[dict[str, Any]], user_prompt: str) -> None:
    """工具轮结束后，提示模型根据工具结果回答用户原问题。"""
    if not any(m.get("role") == "tool" for m in messages):
        return
    messages.append(
        {
            "role": "user",
            "content": (
                f"请根据上述工具返回结果，用一两句口语直接回答用户，不要答非所问。"
                f"用户问题是：{user_prompt}"
            ),
        }
    )


def yield_turn_end(state: VoiceTurnState) -> dict[str, Any]:
    """轮次因打断结束时发送 end_flag，便于前端恢复输入。"""
    return build_chunk_output(
        question_text=None,
        answer_text="",
        end_flag=True,
        user_input_count=state.user_input_count,
        uid=state.uid,
        proactive=state.proactive,
    )


def stream_final_reply(
    client: ToolCallingClient,
    state: VoiceTurnState,
    config: PipelineConfig,
    interruption_event,
) -> Iterator[dict[str, Any]]:
    """最终口语回复：流式分句 yield LLMChunk。"""
    messages = list(state.messages)
    append_tool_synthesis_nudge(messages, state.prompt)
    stream = client.create_stream(
        messages=messages,
        system_prompt=assemble_voice_system_prompt(config.resolved_voice_system_prompt, state.uid),
        max_tokens=config.max_new_tokens,
        temperature=config.temperature,
    )
    llm_state = LLMStreamState()
    for chunk in stream:
        if should_abort_stream(interruption_event):
            logger.info("Voice LLM 流式生成因打断而中止")
            state.interrupted = True
            state.assistant_raw = llm_state.generated_text
            state.assistant_spoken = sanitize_speech_text(llm_state.generated_text)
            yield yield_turn_end(state)
            return
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        llm_state = append_stream_delta(llm_state, delta)
        while not should_abort_stream(interruption_event):
            llm_state, outputs = extract_ready_sentences(
                llm_state,
                prompt=state.prompt,
                audio_input=state.audio_input,
                user_input_count=state.user_input_count,
                uid=state.uid,
                proactive=state.proactive,
            )
            if not outputs:
                break
            for output in outputs:
                yield output

    if should_abort_stream(interruption_event):
        state.interrupted = True
        state.assistant_raw = llm_state.generated_text
        state.assistant_spoken = sanitize_speech_text(llm_state.generated_text)
        yield yield_turn_end(state)
        return

    state.assistant_raw = llm_state.generated_text
    state.assistant_spoken = sanitize_speech_text(llm_state.generated_text)

    if not should_abort_stream(interruption_event):
        llm_state, tail = extract_tail_sentence(
            llm_state,
            prompt=state.prompt,
            audio_input=state.audio_input,
            user_input_count=state.user_input_count,
            uid=state.uid,
            proactive=state.proactive,
        )
        if tail:
            yield tail


def yield_direct_reply(
    text: str,
    state: VoiceTurnState,
) -> Iterator[dict[str, Any]]:
    """首轮已有文本回复时直接输出，避免重复调用 LLM。"""
    spoken = sanitize_speech_text(text)
    state.assistant_raw = text
    state.assistant_spoken = spoken
    yield build_chunk_output(
        question_text=state.prompt if state.audio_input else None,
        answer_text=spoken,
        end_flag=True,
        user_input_count=state.user_input_count,
        uid=state.uid,
        proactive=state.proactive,
    )


def _run_voice_turn_body(
    client: ToolCallingClient,
    runtime: AgentRuntime,
    status_registry: StatusRegistry,
    config: PipelineConfig,
    state: VoiceTurnState,
    interruption_event,
) -> Iterator[dict[str, Any]]:
    """Voice 轮次主体逻辑。"""
    from vocamind.voice.conditions import should_continue_voice_loop, should_stream_final_reply

    handlers = build_voice_handlers(runtime, status_registry, state.user_input_count, state.uid)

    while True:
        if should_abort_stream(interruption_event):
            logger.info("Voice 工具轮因打断而中止")
            state.interrupted = True
            yield yield_turn_end(state)
            return

        response = call_voice_llm(client, state, config)
        assistant = response.choices[0].message
        append_voice_assistant(state.messages, assistant)

        if should_abort_stream(interruption_event):
            logger.info("Voice LLM 响应后检测到打断")
            state.interrupted = True
            yield yield_turn_end(state)
            return

        if should_stream_final_reply(assistant):
            direct = message_text(assistant).strip()
            if direct:
                yield from yield_direct_reply(direct, state)
                return
            yield from stream_final_reply(client, state, config, interruption_event)
            return

        if not should_continue_voice_loop(state, config, assistant):
            append_tool_synthesis_nudge(state.messages, state.prompt)
            yield from stream_final_reply(client, state, config, interruption_event)
            return

        for tc in get_tool_calls(assistant):
            if should_abort_stream(interruption_event):
                logger.info("Voice 工具执行前检测到打断")
                state.interrupted = True
                yield yield_turn_end(state)
                return
            name = tc.function.name
            args = parse_tool_arguments(tc.function.arguments)
            yield build_tool_start(
                tool_call_id=tc.id,
                tool_name=name,
                arguments=args,
                scope="voice",
                uid=state.uid,
                user_input_count=state.user_input_count,
                proactive=state.proactive,
            )
            try:
                handler = handlers.get(name)
                output = call_tool_handler(handler, args, name)
                status = "success"
            except Exception as exc:
                logger.exception("Voice 工具 %s 执行失败", name)
                output = str(exc)
                status = "error"
            yield build_tool_end(
                tool_call_id=tc.id,
                tool_name=name,
                status=status,
                content=str(output),
                scope="voice",
                uid=state.uid,
                user_input_count=state.user_input_count,
                proactive=state.proactive,
            )
            state.messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": str(output)}
            )
        state.tool_round += 1


def _persist_dialogue_session(
    session: DialogueSession,
    state: VoiceTurnState,
    client: ToolCallingClient,
) -> None:
    """轮次结束后写入会话历史并按需压缩。"""
    assistant_text = state.assistant_spoken or state.assistant_raw
    session.record_turn(state.prompt, assistant_text)
    session.compact_if_needed(client.summarize)
    session.save()


def run_voice_turn(
    client: ToolCallingClient,
    runtime: AgentRuntime,
    status_registry: StatusRegistry,
    config: PipelineConfig,
    prompt: str,
    user_input_count: int,
    uid: str | None,
    audio_input: bool,
    interruption_event,
    dialogue_session: DialogueSession,
    proactive: bool = False,
) -> Iterator[dict[str, Any]]:
    """完整 Voice 轮次：始终挂工具，由提示词约束是否调用。"""
    state = VoiceTurnState(
        prompt=prompt,
        user_input_count=user_input_count,
        uid=uid,
        audio_input=audio_input,
        proactive=proactive,
        started_at=now_iso(),
    )
    state.messages = dialogue_session.build_llm_messages(prompt)
    if not proactive:
        inject_voice_notifications(state.messages, runtime)

    system_prompt = assemble_voice_system_prompt(config.resolved_voice_system_prompt, uid)
    try:
        yield from _run_voice_turn_body(
            client, runtime, status_registry, config, state, interruption_event
        )
    finally:
        try:
            _persist_dialogue_session(dialogue_session, state, client)
        except Exception:
            logger.exception("保存对话会话上下文失败")
        try:
            save_voice_turn(build_voice_record(state=state, system_prompt=system_prompt))
        except Exception:
            logger.exception("保存 Voice 对话上下文失败")
