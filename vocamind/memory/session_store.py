"""对话会话上下文：跨轮次历史与摘要压缩。"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from vocamind.common.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_SESSION_DIR = PROJECT_ROOT / ".memory" / "sessions"
MAX_CONTEXT_CHARS = 8000
TARGET_CONTEXT_CHARS = 5000

_lock = threading.Lock()
_session_cache: dict[str, "DialogueSession"] = {}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _message_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


@dataclass
class DialogueSession:
    """单个用户的对话会话状态。"""

    uid: str
    turns: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    updated_at: str = ""
    base_dir: Path = field(default_factory=lambda: DEFAULT_SESSION_DIR)

    @property
    def _path(self) -> Path:
        return self.base_dir / f"{self.uid}.json"

    @classmethod
    def load(cls, uid: str, base_dir: Path | None = None) -> DialogueSession:
        directory = base_dir or DEFAULT_SESSION_DIR
        path = directory / f"{uid}.json"
        if not path.exists():
            return cls(uid=uid, base_dir=directory)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            uid=uid,
            turns=list(data.get("turns") or []),
            summary=str(data.get("summary") or ""),
            updated_at=str(data.get("updated_at") or ""),
            base_dir=directory,
        )

    def save(self) -> None:
        self.updated_at = _now_iso()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "uid": self.uid,
            "summary": self.summary,
            "turns": self.turns,
            "updated_at": self.updated_at,
        }
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def clear_turns(self) -> None:
        """清空对话轮次与摘要，保留 Core Memory 不受影响。"""
        self.turns = []
        self.summary = ""
        self.save()

    def estimate_chars(self) -> int:
        total = len(self.summary)
        total += _message_chars(self.turns)
        return total

    def build_llm_messages(self, current_user_text: str) -> list[dict[str, Any]]:
        """组装送入 LLM 的消息列表（含摘要 + 历史 + 当前用户输入）。"""
        messages: list[dict[str, Any]] = []
        if self.summary.strip():
            messages.append(
                {
                    "role": "user",
                    "content": f"[对话摘要 · 较早轮次]\n{self.summary.strip()}",
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": "好的，我已了解我们之前的对话背景，请继续。",
                }
            )
        messages.extend(self.turns)
        messages.append({"role": "user", "content": current_user_text})
        return messages

    def user_turn_count(self) -> int:
        """历史中的用户消息条数，与 WebSocket user_input_count 对齐。"""
        return sum(1 for t in self.turns if t.get("role") == "user")

    def record_turn(self, user_text: str, assistant_text: str) -> None:
        """记录一轮完整对话。"""
        user_text = user_text.strip()
        assistant_text = assistant_text.strip()
        if user_text:
            self.turns.append({"role": "user", "content": user_text})
        if assistant_text:
            self.turns.append({"role": "assistant", "content": assistant_text})

    def _format_turns_for_summary(self, turns: list[dict[str, str]]) -> str:
        lines = []
        for msg in turns:
            role = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role}：{msg.get('content', '')}")
        return "\n".join(lines)

    def compact_if_needed(self, summarizer: Callable[[str], str]) -> None:
        """超过上限时摘要前一半对话，替换旧摘要，总体压到目标字数以下。"""
        from vocamind.memory.prompts import DIALOGUE_SUMMARY_PROMPT

        while self.estimate_chars() > MAX_CONTEXT_CHARS and len(self.turns) >= 2:
            mid = len(self.turns) // 2
            first_half = self.turns[:mid]
            second_half = self.turns[mid:]
            parts = []
            if self.summary.strip():
                parts.append(f"已有摘要：\n{self.summary.strip()}")
            parts.append("待压缩对话：\n" + self._format_turns_for_summary(first_half))
            prompt = DIALOGUE_SUMMARY_PROMPT + "\n\n" + "\n\n".join(parts)
            try:
                new_summary = summarizer(prompt).strip()
            except Exception:
                logger.exception("对话摘要失败，改用截断")
                new_summary = self._format_turns_for_summary(first_half)[:1500]
            self.summary = new_summary
            self.turns = second_half
            logger.info(
                "对话上下文已压缩 uid=%s chars=%d summary_len=%d turns=%d",
                self.uid,
                self.estimate_chars(),
                len(self.summary),
                len(self.turns),
            )
            if self.estimate_chars() <= TARGET_CONTEXT_CHARS:
                break
            if len(self.turns) < 2:
                break


def get_dialogue_session(uid: str | None, base_dir: Path | None = None) -> DialogueSession:
    key = (uid or "default").strip() or "default"
    with _lock:
        if base_dir is not None:
            return DialogueSession.load(key, base_dir)
        if key not in _session_cache:
            _session_cache[key] = DialogueSession.load(key)
        return _session_cache[key]
