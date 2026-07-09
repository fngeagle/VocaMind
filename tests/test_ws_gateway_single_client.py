"""WebSocket 网关单活跃连接测试。"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from vocamind.common import PipelineConfig
from vocamind.pipeline import PipelineContext
from vocamind.pipeline.factories import create_gateway


@pytest.mark.asyncio
async def test_outbound_dispatcher_sends_to_active_ws():
    ctx = PipelineContext.create()
    config = PipelineConfig()
    with patch("vocamind.gateway.server.VADProcessor"):
        gateway = create_gateway(ctx, config)

    mock_ws = AsyncMock()
    gateway._active_ws = mock_ws
    ctx.outbound_queue.put(
        {
            "uid": "u1",
            "user_input_count": 1,
            "answer_text": "hi",
            "answer_audio": "",
            "end_flag": True,
        }
    )

    task = asyncio.create_task(gateway._outbound.run())
    await asyncio.sleep(0.3)
    ctx.stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    mock_ws.send.assert_called()
    payload = json.loads(mock_ws.send.call_args[0][0])
    assert payload["answer_text"] == "hi"


@pytest.mark.asyncio
async def test_outbound_drops_when_no_active_ws():
    ctx = PipelineContext.create()
    config = PipelineConfig()
    with patch("vocamind.gateway.server.VADProcessor"):
        gateway = create_gateway(ctx, config)

    ctx.outbound_queue.put({"uid": "u1", "answer_text": "lost", "end_flag": True})
    ctx.stop_event.set()

    await gateway._outbound.run()
