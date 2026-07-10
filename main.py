"""VocaMind S2S 命令行入口。"""
import vocamind.common.env  # noqa: F401  启动时加载 .env

import argparse
import logging
import os
import socket
import sys

from vocamind.common import PipelineConfig, ReplyMode
from vocamind.common.paths import DEFAULT_REF_DIR
from vocamind.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def ensure_port_available(host: str, port: int) -> None:
    """启动前检测端口是否可用，避免多实例静默抢占。"""
    bind_host = host if host != "0.0.0.0" else ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((bind_host, port))
    except OSError as exc:
        logger.error(
            "端口 %s:%s 已被占用（%s）。请先关闭其他 main.py 实例。",
            host,
            port,
            exc,
        )
        sys.exit(1)
    finally:
        sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="VocaMind 轻量语音对话管道")
    parser.add_argument("--ws-host", default="0.0.0.0", help="WebSocket 监听地址")
    parser.add_argument("--ws-port", type=int, default=9001, help="WebSocket 监听端口")
    parser.add_argument("--reply-mode", choices=["audio", "text"], default="audio", help="助手回复形式")
    parser.add_argument("--enable-interruption", action="store_true", default=True)
    parser.add_argument("--no-interruption", action="store_true", help="禁用用户打断")
    parser.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "deepseek-chat"))
    parser.add_argument("--llm-url", default=os.getenv("LLM_API_URL"))
    parser.add_argument("--voice-llm-model", default=os.getenv("VOICE_LLM_MODEL"))
    parser.add_argument("--voice-llm-url", default=os.getenv("VOICE_LLM_API_URL"))
    parser.add_argument("--agent-llm-model", default=os.getenv("AGENT_LLM_MODEL"))
    parser.add_argument("--agent-llm-url", default=os.getenv("AGENT_LLM_API_URL"))
    parser.add_argument("--agent-tasks-dir", default=os.getenv("AGENT_TASKS_DIR"))
    parser.add_argument("--agent-workdir", default=os.getenv("AGENT_WORKDIR"))
    parser.add_argument("--tts-model", default="FunAudioLLM/CosyVoice2-0.5B")
    parser.add_argument(
        "--ref-dir",
        default=os.getenv("REF_DIR", str(DEFAULT_REF_DIR)),
        help="TTS 参考音色目录（含 ref.json 和 ref_wav/*.wav）",
    )
    parser.add_argument("--system-prompt", default=None)
    parser.add_argument("--chat-size", type=int, default=5)
    args = parser.parse_args()

    ensure_port_available(args.ws_host, args.ws_port)

    config = PipelineConfig(
        ws_host=args.ws_host,
        ws_port=args.ws_port,
        reply_mode=ReplyMode(args.reply_mode),
        enable_interruption=not args.no_interruption,
        llm_model=args.llm_model,
        llm_api_url=args.llm_url,
        voice_llm_model=args.voice_llm_model,
        voice_llm_api_url=args.voice_llm_url,
        agent_llm_model=args.agent_llm_model,
        agent_llm_api_url=args.agent_llm_url,
        agent_tasks_dir=args.agent_tasks_dir,
        agent_workdir=args.agent_workdir,
        tts_model=args.tts_model,
        ref_dir=args.ref_dir,
        chat_size=args.chat_size,
    )
    if args.system_prompt:
        config.system_prompt = args.system_prompt

    run_pipeline(config)


if __name__ == "__main__":
    main()
