"""LLM 流式推理过程中的可变状态。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMStreamState:
    generated_text: str = ""
    printable_text: str = ""
    sentence_count: int = 0
    first_token_logged: bool = False
