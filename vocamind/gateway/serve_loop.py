"""WebSocket 网关服务循环的单步与串联逻辑。"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

import websockets

from vocamind.gateway.conditions import should_continue_gateway, should_retry_after_bind_error

if TYPE_CHECKING:
    from vocamind.gateway.server import WebSocketGateway

logger = logging.getLogger(__name__)

# 运行服务周期
async def run_serve_cycle(gateway: WebSocketGateway) -> None:
    """一次服务周期：绑定端口、启动出站分发、等待停止信号。"""
    # 出站分发任务
    dispatcher_task: Optional[asyncio.Task] = None
    try:
        # 连接会话生命周期信号
        gateway.session_lifecycle.signal_connect()
        # 绑定端口
        gateway.server = await websockets.serve(
            gateway._handle_connection,
            gateway.host,
            gateway.port,
            ping_interval=None,
            ping_timeout=None,
        )
        # 创建出站分发任务
        dispatcher_task = asyncio.create_task(gateway._outbound.run())
        logger.info("WebSocket 服务启动于 %s:%s", gateway.host, gateway.port)
        # 循环直到停止事件触发
        while should_continue_gateway(gateway.stop_event):
            # 等待 0.2 秒
            await asyncio.sleep(0.2)
    except OSError as exc:
        if should_retry_after_bind_error(exc):
            logger.error(
                "WebSocket 绑定 %s:%s 失败: %s，3 秒后重试",
                gateway.host,
                gateway.port,
                exc,
            )
            await asyncio.sleep(3)
        else:
            raise
    except websockets.exceptions.InvalidState:
        logger.error("WebSocket 状态异常，正在重启...")
    finally:
        if dispatcher_task is not None:
            dispatcher_task.cancel()
            try:
                await dispatcher_task
            except asyncio.CancelledError:
                pass
        if gateway.server:
            gateway.server.close()
            await gateway.server.wait_closed()
            gateway.server = None
        gateway._active_ws = None
        if should_continue_gateway(gateway.stop_event):
            await asyncio.sleep(0.1)
