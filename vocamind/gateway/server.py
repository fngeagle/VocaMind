"""单端口 WebSocket 服务入口。"""
from __future__ import annotations

import asyncio
import json
import logging
from queue import Queue
from threading import Event
from typing import Optional

import websockets

from vocamind.common.config import PipelineConfig
from vocamind.gateway.conditions import should_continue_gateway
from vocamind.gateway.inbound import InboundRouter
from vocamind.gateway.outbound import OutboundDispatcher
from vocamind.gateway.serve_loop import run_serve_cycle
from vocamind.gateway.session import ClientSession
from vocamind.gateway.session_signals import SessionSignals
from vocamind.gateway.vad import VADProcessor

logger = logging.getLogger(__name__)


class WebSocketGateway:
    """统一 WebSocket 服务：同一连接上收发 JSON 消息。"""

    def __init__(
        self,
        *,
        stop_event: Event,
        should_listen: Event,
        interruption_event: Event,
        assistant_turn_active: Event,
        session_lifecycle: SessionSignals,
        spoken_prompt_queue: Queue,
        lm_response_queue: Queue,
        outbound_queue: Queue,
        config: PipelineConfig,
    ) -> None:
        self.stop_event = stop_event
        self.session_lifecycle = session_lifecycle
        self.should_listen = should_listen
        self.host = config.ws_host
        self.port = config.ws_port
        self.server = None
        self._active_ws: Optional[websockets.WebSocketServerProtocol] = None
        self._conn_generation = 0
        self._active_gen = 0
        self._ws_lock = asyncio.Lock()

        vad = VADProcessor(
            should_listen,
            interruption_event,
            chunk_size=config.chunk_size,
            enable_interruption=config.enable_interruption,
            thresh=config.vad_thresh,
            sample_rate=config.sample_rate,
            min_silence_ms=config.min_silence_ms,
            min_speech_ms=config.min_speech_ms,
            vad_model_path=config.vad_model_path,
            vad_use_gpu=config.vad_use_gpu,
        )
        self._inbound = InboundRouter(
            spoken_prompt_queue,
            should_listen,
            session_lifecycle,
            vad,
            assistant_turn_active,
            interruption_event,
            lm_response_queue,
            outbound_queue,
        )
        self._outbound = OutboundDispatcher(
            outbound_queue,
            stop_event,
            self._get_active_ws,
            self._unregister_connection,
            self._ws_lock,
        )

    def _get_active_ws(self) -> Optional[websockets.WebSocketServerProtocol]:
        return self._active_ws

    async def _claim_connection(self, ws: websockets.WebSocketServerProtocol) -> int:
        """抢占最新连接槽位，并返回本会话的世代号。"""
        old_ws: Optional[websockets.WebSocketServerProtocol]
        async with self._ws_lock:
            self._conn_generation += 1
            gen = self._conn_generation
            old_ws = self._active_ws
            self._active_ws = ws
            self._active_gen = gen
            self.session_lifecycle.signal_connect()

        if old_ws is not None and old_ws is not ws:
            logger.info("关闭先前的 WebSocket 连接，仅保留最新客户端")
            try:
                await old_ws.close()
            except Exception:
                pass

        return gen

    def _is_active_connection(self, gen: int) -> bool:
        return self._active_gen == gen

    async def _release_connection(self, ws: websockets.WebSocketServerProtocol, gen: int) -> None:
        """仅当本会话仍是当前最新连接时才释放活跃槽位。"""
        async with self._ws_lock:
            if self._active_gen != gen:
                return
            if self._active_ws is ws:
                self._active_ws = None
            self.session_lifecycle.signal_disconnect()

    async def _unregister_connection(self, ws: websockets.WebSocketServerProtocol) -> None:
        """出站推送失败时按连接对象释放（供 OutboundDispatcher 调用）。"""
        async with self._ws_lock:
            if self._active_ws is ws:
                self._active_ws = None
                self.session_lifecycle.signal_disconnect()

    async def _handle_connection(self, ws: websockets.WebSocketServerProtocol) -> None:
        gen = await self._claim_connection(ws)
        if not self._is_active_connection(gen):
            logger.info("WebSocket 连接已被更新的客户端取代，放弃本会话")
            return

        session = ClientSession()
        logger.info("WebSocket 客户端已连接")
        self.should_listen.set()
        await ws.send(json.dumps({"type": "ready"}))

        try:
            await self._inbound.run_loop(ws, session)
        finally:
            was_active = self._is_active_connection(gen)
            await self._release_connection(ws, gen)
            if was_active:
                logger.info("WebSocket 会话结束")
            else:
                logger.info("WebSocket 会话结束（已被新连接取代）")

    async def _serve_loop(self) -> None:
        while should_continue_gateway(self.stop_event):
            await run_serve_cycle(self)

    def start(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._serve_loop())
        except KeyboardInterrupt:
            logger.info("WebSocket 网关被用户中断")
        except Exception:
            logger.exception("WebSocket 网关线程异常退出")
        finally:
            loop.run_until_complete(self.shutdown())
            loop.close()

    async def shutdown(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        self._active_ws = None

    async def stop(self) -> None:
        self.stop_event.set()
        await self.shutdown()
