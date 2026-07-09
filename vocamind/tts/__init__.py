"""语音合成功能模块。"""
from vocamind.tts.api import APITTSHandler
from vocamind.tts.passthrough import PassthroughTTSHandler

__all__ = ["APITTSHandler", "PassthroughTTSHandler"]
