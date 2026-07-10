"""管道配置：通过参数化方式支持不同 TTS/LLM 后端与回复模式。"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from vocamind.common.paths import DEFAULT_REF_DIR


class ReplyMode(str, Enum):
    """助手回复形式。"""
    AUDIO = "audio"
    TEXT = "text"


class TTSBackend(str, Enum):
    """语音合成后端。"""
    API = "api"
    NONE = "none"


@dataclass
class PipelineConfig:
    """S2S 管道运行参数。"""

    # WebSocket（单端口双向）
    ws_host: str = "0.0.0.0"
    ws_port: int = 9001
    http_host: str = "0.0.0.0"
    http_port: int = 9002
    enable_interruption: bool = True

    # 回复模式
    reply_mode: ReplyMode = ReplyMode.AUDIO

    # LLM（OpenAI 兼容接口，保留作 Voice 默认）
    llm_model: str = "deepseek-chat"
    llm_api_url: Optional[str] = None
    llm_api_key_env: str = "LLM_API_KEY"
    max_new_tokens: int = 512
    temperature: float = 0.7
    chat_size: int = 5
    system_prompt: str = "你是一个简洁、友好的语音助手，回答尽量口语化，避免使用 markdown 格式,不要使用 emoji。"

    # Voice LLM（对话前台：派发任务 + 查询状态）
    voice_llm_model: Optional[str] = None
    voice_llm_api_url: Optional[str] = None
    voice_llm_api_key_env: str = "LLM_API_KEY"
    voice_system_prompt: str = (
        "你是语音对话助手。"
        "工具始终可用，但默认不要调用；能用一句话直接回答的就直接回答。"
        "回答口语化，避免 markdown 和 emoji。"
    )
    voice_max_tool_rounds: int = 2

    # Agent LLM（执行后台：完整 tool loop）
    agent_llm_model: Optional[str] = None
    agent_llm_api_url: Optional[str] = None
    agent_llm_api_key_env: str = "AGENT_LLM_API_KEY"
    agent_system_prompt: str = (
        "你是后台执行 Agent。根据任务描述完成工作，使用可用工具。"
        "任务结束前必须给出可播报的事实摘要：包含关键结论、数据或发现，"
        "禁止只说「以上即为完整结果」「任务已完成」等空话。"
        "若用 write_file 写入了文档，请保存为 .md 格式，"
        "最终回复里也要概括文档要点；用户可在界面点击查看完整文档。"
        "web_search 每个任务最多 10 次，应合并关键词、复用已有结果，避免重复细搜。"
        "完成后调用 complete_task 标记任务完成。"
    )
    agent_max_tokens: int = 4096
    agent_tasks_dir: Optional[str] = None
    agent_workdir: Optional[str] = None

    # TTS
    tts_backend: TTSBackend = TTSBackend.API
    tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    tts_api_url: str = "https://api.siliconflow.cn/v1"
    tts_api_key_env: str = "ASR_TTS_API_KEY"
    ref_dir: str = str(DEFAULT_REF_DIR)
    tts_sample_rate: int = 32000

    # 打断时的过渡语
    interruption_transitions: list[str] = field(
        default_factory=lambda: ["好，稍等一下。", "嗯，明白了，等等哈。", "这样呀，我想想。"]
    )

    @property
    def resolved_voice_llm_model(self) -> str:
        return self.voice_llm_model or self.llm_model

    @property
    def resolved_voice_llm_api_url(self) -> Optional[str]:
        return self.voice_llm_api_url or self.llm_api_url

    @property
    def resolved_voice_llm_api_key_env(self) -> str:
        return self.voice_llm_api_key_env or self.llm_api_key_env

    @property
    def resolved_voice_system_prompt(self) -> str:
        return self.voice_system_prompt or self.system_prompt

    @property
    def resolved_agent_llm_model(self) -> str:
        return self.agent_llm_model or self.llm_model

    @property
    def resolved_agent_llm_api_url(self) -> Optional[str]:
        return self.agent_llm_api_url or self.llm_api_url

    @property
    def resolved_agent_llm_api_key_env(self) -> str:
        import os

        if os.getenv(self.agent_llm_api_key_env):
            return self.agent_llm_api_key_env
        return self.llm_api_key_env
