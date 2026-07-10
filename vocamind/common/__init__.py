"""跨功能共享模块。"""
from .config import PipelineConfig, ReplyMode, TTSBackend
from .handler import BaseHandler, ThreadManager
from .paths import DEFAULT_REF_DIR, PROJECT_ROOT
from .protocols import PipelineNode

__all__ = [
    "BaseHandler",
    "DEFAULT_REF_DIR",
    "PipelineConfig",
    "PipelineNode",
    "PROJECT_ROOT",
    "ReplyMode",
    "ThreadManager",
    "TTSBackend",
]
