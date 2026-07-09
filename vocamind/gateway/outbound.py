"""WebSocket 出站分发：管道回复推送到活跃连接。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from queue import Empty, Queue
from threading import Event
from typing import Optional

import websockets

from vocamind.common.timing import log_elapsed
from vocamind.gateway.codec import OutboundJsonEncoder, normalize_outbound_audio

logger = logging.getLogger(__name__)


class OutboundDispatcher:
    """全局唯一出站循环，将 outbound_queue 消息发给当前活跃 WebSocket。"""

    def __init__(
        self,
        outbound_queue: Queue,
        stop_event: Event,
        get_active_ws,
        unregister_ws,
        ws_lock: asyncio.Lock,
    ) -> None:
        self.outbound_queue = outbound_queue
        self.stop_event = stop_event
        self._get_active_ws = get_active_ws
        self._unregister_ws = unregister_ws
        self._ws_lock = ws_lock

    async def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                data = await asyncio.to_thread(self.outbound_queue.get, True, 0.5)
            except Empty:
                continue

            async with self._ws_lock:
                ws = self._get_active_ws()

            if ws is None:
                logger.warning("无活跃 WebSocket，出站消息已丢弃: uid=%s", data.get("uid"))
                continue

            send_start = time.perf_counter()
            if data.get("stop_playback"):
                try:
                    await ws.send(json.dumps({"stop_playback": True, "uid": data.get("uid")}))
                except websockets.ConnectionClosedError:
                    logger.warning("推送 stop_playback 时连接已关闭")
                    await self._unregister_ws(ws)
                except websockets.ConnectionClosedOK:
                    await self._unregister_ws(ws)
                continue

            normalize_start = time.perf_counter()
            normalize_outbound_audio(data)
            log_elapsed("WS出站 编码", normalize_start, uid=data.get("uid"))
            try:
                await ws.send(json.dumps(data, cls=OutboundJsonEncoder))
                log_elapsed(
                    "WS出站 推送",
                    send_start,
                    uid=data.get("uid"),
                    count=data.get("user_input_count"),
                    end_flag=data.get("end_flag"),
                    text=(data.get("answer_text") or "")[:40],
                )
            except websockets.ConnectionClosedError:
                logger.warning("推送回复时连接已关闭，消息已丢弃")
                await self._unregister_ws(ws)
            except websockets.ConnectionClosedOK:
                await self._unregister_ws(ws)
