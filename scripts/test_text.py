"""命令行文本测试：向 VocaMind 后端发送文字，流式打印回复并可选播放音频。"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import tempfile
import uuid
import wave

import websockets

SAMPLE_RATE = 16000


def play_pcm(pcm: bytes) -> None:
    """播放 int16 mono PCM（Windows 用 winsound，其它平台写临时 wav 后播放）。"""
    if not pcm:
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    try:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm)
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            import miniaudio
            import time

            stream = miniaudio.stream_file(path)
            device = miniaudio.PlaybackDevice()
            device.start(stream)
            while device.running:
                time.sleep(0.05)
    finally:
        os.unlink(path)


async def test_text(
    text: str,
    ws_url: str = "ws://localhost:9001",
    timeout: float = 120.0,
    play_audio: bool = False,
) -> None:
    uid = str(uuid.uuid4())
    user_input_count = 1
    assistant_parts: list[str] = []

    async with websockets.connect(ws_url, ping_interval=None, ping_timeout=None) as ws:
        print(f"[WebSocket] 已连接 {ws_url}")

        # 握手就绪消息（可选）
        try:
            ready = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(ready)
            if data.get("type") == "ready":
                print("[WebSocket] 服务端就绪")
        except (asyncio.TimeoutError, json.JSONDecodeError):
            pass

        await ws.send(json.dumps({"uid": uid, "text": text}))
        print(f"[用户] {text}")

        ack = await asyncio.wait_for(ws.recv(), timeout=10)
        print(f"[确认] {ack}")

        got_end = False
        while not got_end:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(raw)
            if data.get("type") == "ready":
                continue
            if data.get("uid") != uid:
                continue
            if data.get("user_input_count") != user_input_count:
                continue

            answer = data.get("answer_text", "")
            audio_b64 = data.get("answer_audio", "")
            end_flag = data.get("end_flag", False)

            if answer:
                assistant_parts.append(answer)
                print(f"[助手] {answer}", flush=True)
            if audio_b64 and audio_b64 not in ("", 0):
                audio_bytes = base64.b64decode(audio_b64)
                print(f"[音频] {len(audio_bytes)} 字节 PCM", flush=True)
                if play_audio:
                    await asyncio.to_thread(play_pcm, audio_bytes)
            if end_flag:
                full = "".join(assistant_parts)
                print(f"[完成] 本轮回复结束（共 {len(full)} 字）")
                got_end = True


def main() -> None:
    parser = argparse.ArgumentParser(description="VocaMind 文本对话测试")
    parser.add_argument("text", nargs="?", default="你好，请用一句话介绍你自己")
    parser.add_argument("--ws-url", default="ws://localhost:9001", help="WebSocket 地址")
    parser.add_argument("--timeout", type=float, default=120.0, help="等待单条回复的超时（秒）")
    parser.add_argument("--play", action="store_true", help="收到音频后立即播放")
    args = parser.parse_args()

    try:
        asyncio.run(
            test_text(
                args.text,
                args.ws_url,
                args.timeout,
                play_audio=args.play,
            )
        )
    except TimeoutError:
        print("[错误] 等待回复超时，请确认后端已启动且 API Key 配置正确", file=sys.stderr)
        sys.exit(1)
    except ConnectionRefusedError:
        print("[错误] 无法连接 WebSocket，请先运行: python main.py", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
