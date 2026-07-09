"""Voice LLM 编排状态。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VoiceTurnState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_round: int = 0
    uid: Optional[str] = None
    user_input_count: int = 0
    audio_input: bool = False
    prompt: str = ""
    proactive: bool = False
    started_at: str = ""
    assistant_raw: str = ""
    assistant_spoken: str = ""
    interrupted: bool = False
