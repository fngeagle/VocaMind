"""WebSocket 入站消息路由：客户端完成 ASR 后发送文本。"""
from __future__ import annotations

import asyncio
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
from vocamind.memory import get_dialogue_session
from vocamind.pipeline.interruption import trigger_interruption_queues

logger = logging.getLogger(__name__)


class InboundRouter:
    """解析客户端 JSON 消息并写入 text_prompt 队列。"""

    def __init__(
        self,
        text_prompt_queue: Queue,
        session_lifecycle: SessionSignals,
        assistant_turn_active: Event,
        interruption_event: Event,
        lm_response_queue: Queue,
        outbound_queue: Queue,
    ) -> None:
        self.text_prompt_queue = text_prompt_queue
        self.session_lifecycle = session_lifecycle
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

            msg_type = json_data.get("type")
            if msg_type == "sync_history":
                await self._handle_sync_history(ws, session, uid)
                continue

            is_playing = json_data.get("is_playing", "placeholder")
            if is_playing in ("true", "false"):
                session.frontend_is_playing = is_playing == "true"

            text = json_data.get("text")
            if text is not None:
                await self._handle_text(ws, session, uid, text, json_data)
            elif json_data.get("audio") is not None:
                logger.warning("已忽略 audio 消息：ASR 已移至客户端，请发送 text")
                await ws.send(json.dumps({"placeholder": ""}))

    async def _handle_sync_history(
        self,
        ws: websockets.WebSocketServerProtocol,
        session: ClientSession,
        uid: Optional[str],
    ) -> None:
        """客户端重连后拉取后端持久化的对话历史。"""
        try:
            if not uid:
                await ws.send(
                    json.dumps(
                        {
                            "type": "history_sync",
                            "uid": None,
                            "turns": [],
                            "user_input_count": 0,
                        }
                    )
                )
                return

            session.bind_uid(uid)
            dialogue = get_dialogue_session(uid)
            user_count = dialogue.user_turn_count()
            session.user_input_count = user_count
            await ws.send(
                json.dumps(
                    {
                        "type": "history_sync",
                        "uid": uid,
                        "turns": dialogue.turns,
                        "user_input_count": user_count,
                        "has_summary": bool(dialogue.summary.strip()),
                    },
                    ensure_ascii=False,
                )
            )
            logger.info(
                "已同步对话历史 uid=%s turns=%d user_input_count=%d",
                uid,
                len(dialogue.turns),
                user_count,
            )
        except Exception:
            logger.exception("历史同步失败 uid=%s", uid)
            await ws.send(
                json.dumps(
                    {
                        "type": "history_sync",
                        "uid": uid,
                        "turns": [],
                        "user_input_count": 0,
                        "error": "sync_failed",
                    }
                )
            )

    async def _handle_text(
        self,
        ws: websockets.WebSocketServerProtocol,
        session: ClientSession,
        uid: Optional[str],
        text: str,
        json_data: dict,
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
        self.text_prompt_queue.put(
            {
                "data": text,
                "user_input_count": session.user_input_count,
                "uid": uid,
                "audio_input": bool(json_data.get("audio_input", False)),
            }
        )
        await ws.send(json.dumps({"placeholder": ""}))
        log_elapsed(
            "WS入站 文本",
            total_start,
            uid=uid,
            count=session.user_input_count,
            text=text[:40],
            audio_input=bool(json_data.get("audio_input", False)),
        )
