"""WebSocket 入站消息路由：文本 / 音频 / VAD。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from queue import Queue
from threading import Event
from typing import Optional

import websockets

from vocamind.gateway.session_signals import SessionSignals
from vocamind.common.timing import log_elapsed
from vocamind.gateway.session import ClientSession
from vocamind.gateway.vad import VADProcessor
from vocamind.memory import get_dialogue_session
from vocamind.pipeline.interruption import trigger_interruption_queues

logger = logging.getLogger(__name__)


class InboundRouter:
    """解析客户端 JSON 消息并写入 prompt 队列。"""

    def __init__(
        self,
        prompt_queue: Queue,
        should_listen: Event,
        session_lifecycle: SessionSignals,
        vad: VADProcessor,
        assistant_turn_active: Event,
        interruption_event: Event,
        lm_response_queue: Queue,
        outbound_queue: Queue,
    ) -> None:
        self.prompt_queue = prompt_queue
        self.should_listen = should_listen
        self.session_lifecycle = session_lifecycle
        self._vad = vad
        self.assistant_turn_active = assistant_turn_active
        self.interruption_event = interruption_event
        self.lm_response_queue = lm_response_queue
        self.outbound_queue = outbound_queue

    def _should_interrupt(self, session: ClientSession) -> bool:
        return session.frontend_is_playing or self.assistant_turn_active.is_set()

    def _trigger_user_interruption(self, session: ClientSession) -> bool:
        """用户新输入时打断当前助手轮次并清下游积压，返回是否触发了打断。"""
        if not self._should_interrupt(session):
            return False
        self._vad.maybe_interrupt_user_input(
            frontend_is_playing=session.frontend_is_playing,
            assistant_turn_active=self.assistant_turn_active.is_set(),
        )
        trigger_interruption_queues(
            self.interruption_event,
            self.lm_response_queue,
            self.outbound_queue,
        )
        return True

    async def _send_stop_playback(
        self,
        ws: websockets.WebSocketServerProtocol,
        uid: Optional[str],
    ) -> None:
        """通知前端立即停止音频播放。"""
        await ws.send(json.dumps({"stop_playback": True, "uid": uid}))

    async def run_loop(
        self,
        ws: websockets.WebSocketServerProtocol,
        session: ClientSession,
    ) -> None:
        while True:
            try:
                res = await ws.recv()
            except websockets.ConnectionClosedOK:
                logger.info("WebSocket 连接正常关闭")
                break
            except websockets.ConnectionClosedError as exc:
                logger.error("WebSocket 连接异常关闭: %s", exc)
                break

            if res.startswith("ConnectionClosedError"):
                await ws.send(json.dumps({"placeholder": ""}))
                break
            if res.startswith("ConnectionClosedOK"):
                await ws.send(json.dumps({"placeholder": ""}))
                session.reset_topic()
                self.session_lifecycle.signal_new_topic()
                continue

            try:
                json_data = json.loads(res)
            except json.JSONDecodeError:
                logger.warning("无法解析入站 JSON，已忽略")
                continue

            uid = json_data.get("uid")
            if uid:
                session.bind_uid(uid)

            is_playing = json_data.get("is_playing", "placeholder")
            if is_playing in ("true", "false"):
                session.frontend_is_playing = is_playing == "true"

            text = json_data.get("text")
            audio = json_data.get("audio")

            if text is not None:
                await self._handle_text(ws, session, uid, text)
            elif audio is not None:
                await self._handle_audio(ws, session, uid, audio)

    async def _handle_text(
        self,
        ws: websockets.WebSocketServerProtocol,
        session: ClientSession,
        uid: Optional[str],
        text: str,
    ) -> None:
        total_start = time.perf_counter()
        if text == "new topic":
            await ws.send(json.dumps({"placeholder": ""}))
            session.reset_topic()
            self.session_lifecycle.signal_new_topic()
            if session.uid:
                get_dialogue_session(session.uid).clear_turns()
            return

        interrupted = self._trigger_user_interruption(session)
        if interrupted:
            await self._send_stop_playback(ws, uid)

        session.user_input_count += 1
        self.prompt_queue.put(
            {"data": text, "user_input_count": session.user_input_count, "uid": uid}
        )
        await ws.send(json.dumps({"placeholder": ""}))
        log_elapsed("WS入站 文本", total_start, uid=uid, count=session.user_input_count, text=text[:40])

    async def _handle_audio(
        self,
        ws: websockets.WebSocketServerProtocol,
        session: ClientSession,
        uid: Optional[str],
        audio_b64: str,
    ) -> None:
        total_start = time.perf_counter()
        vad_detected = False
        interrupted = False
        decode_start = time.perf_counter()
        audio_bytes = base64.b64decode(audio_b64)
        chunk_size = self._vad.chunk_size
        chunk_count = len(audio_bytes) // chunk_size
        log_elapsed("WS入站 音频解码", decode_start, bytes=len(audio_bytes), chunks=chunk_count)

        assistant_active = self.assistant_turn_active.is_set()
        if self.should_listen.is_set():
            for i in range(chunk_count):
                chunk = audio_bytes[i * chunk_size : (i + 1) * chunk_size]
                vad_start = time.perf_counter()
                vad_result = await asyncio.to_thread(
                    self._vad.process_chunk,
                    chunk,
                    session.frontend_is_playing,
                    assistant_active,
                )
                if not interrupted and self._vad.last_speech_started and self.interruption_event.is_set():
                    trigger_interruption_queues(
                        self.interruption_event,
                        self.lm_response_queue,
                        self.outbound_queue,
                    )
                    await self._send_stop_playback(ws, uid)
                    interrupted = True

                if vad_result is not None:
                    log_elapsed("WS入站 VAD命中", vad_start, chunk_index=i + 1, uid=uid)
                    if not interrupted:
                        interrupted = self._trigger_user_interruption(session)
                        if interrupted:
                            await self._send_stop_playback(ws, uid)
                    session.user_input_count += 1
                    self.prompt_queue.put(
                        {
                            "data": vad_result,
                            "user_input_count": session.user_input_count,
                            "uid": uid,
                        }
                    )
                    await ws.send(json.dumps({"return_info": "VAD detected"}))
                    vad_detected = True

        if not vad_detected:
            await ws.send(json.dumps({"placeholder": ""}))

        log_elapsed(
            "WS入站 音频总计",
            total_start,
            uid=uid,
            vad_hit=vad_detected,
            chunks=chunk_count,
        )
