"""OpenAI 兼容 function calling 客户端与工具辅助函数。"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY_MS = 500


@dataclass
class RecoveryState:
    has_escalated: bool = False
    recovery_count: int = 0
    consecutive_429: int = 0
    has_attempted_reactive_compact: bool = False
    current_model: str = ""


def to_openai_tools(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 {name, description, input_schema} 转为 OpenAI tools 格式。"""
    result = []
    for tool in tool_defs:
        schema = tool.get("input_schema") or tool.get("parameters") or {"type": "object", "properties": {}}
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": schema,
                },
            }
        )
    return result


def has_tool_calls(message: Any) -> bool:
    tool_calls = getattr(message, "tool_calls", None)
    return bool(tool_calls)


def get_tool_calls(message: Any) -> list[Any]:
    return list(getattr(message, "tool_calls", None) or [])


def message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    return content or ""


def retry_delay(attempt: int) -> float:
    base = min(BASE_DELAY_MS * (2**attempt), 32000) / 1000
    return base + random.uniform(0, base * 0.25)


def is_prompt_too_long_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        ("prompt" in msg and "long" in msg)
        or "context_length_exceeded" in msg
        or "max_context_window" in msg
    )


class ToolCallingClient:
    """带重试的 OpenAI function calling 客户端。"""

    def __init__(
        self,
        *,
        model: str,
        api_url: Optional[str],
        api_key_env: str,
        fallback_model: Optional[str] = None,
    ) -> None:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"环境变量 {api_key_env} 未设置")
        self.client = OpenAI(api_key=api_key, base_url=api_url)
        self.model = model
        self.fallback_model = fallback_model
        self.recovery = RecoveryState(current_model=model)

    def create(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> Any:
        full_messages: list[dict[str, Any]] = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        openai_tools = to_openai_tools(tools) if tools else None

        def _call():
            kwargs: dict[str, Any] = {
                "model": self.recovery.current_model or self.model,
                "messages": full_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": stream,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
            return self.client.chat.completions.create(**kwargs)

        return self._with_retry(_call)

    def create_stream(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["stream"] = True
        return self.create(*args, **kwargs)

    def _with_retry(self, fn: Callable[[], Any]) -> Any:
        for attempt in range(MAX_RETRIES):
            try:
                result = fn()
                self.recovery.consecutive_429 = 0
                return result
            except Exception as exc:
                msg = str(exc).lower()
                if "429" in msg or "rate" in msg:
                    delay = retry_delay(attempt)
                    logger.warning("LLM 429，%.1fs 后重试 (%d/%d)", delay, attempt + 1, MAX_RETRIES)
                    time.sleep(delay)
                    continue
                if "529" in msg or "overloaded" in msg:
                    self.recovery.consecutive_429 += 1
                    if self.recovery.consecutive_429 >= 2 and self.fallback_model:
                        self.recovery.current_model = self.fallback_model
                        self.recovery.consecutive_429 = 0
                    delay = retry_delay(attempt)
                    logger.warning("LLM 529，%.1fs 后重试", delay)
                    time.sleep(delay)
                    continue
                raise
        raise RuntimeError(f"Max retries ({MAX_RETRIES}) exceeded")

    def summarize(self, text: str, max_tokens: int = 2000) -> str:
        response = self.create(
            messages=[{"role": "user", "content": text}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return message_text(response.choices[0].message)


def parse_tool_arguments(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
