"""用户 Core Memory 持久化存储。"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from vocamind.common.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

MemoryCategory = Literal["profile", "habit", "preference", "constraint"]

DEFAULT_MEMORY_DIR = PROJECT_ROOT / ".memory" / "core"
VALID_CATEGORIES = frozenset({"profile", "habit", "preference", "constraint"})

_lock = threading.Lock()
_store_cache: dict[str, "CoreMemoryStore"] = {}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class CoreMemoryEntry:
    key: str
    value: str
    category: str = "profile"
    updated_at: str = ""


@dataclass
class CoreMemoryDocument:
    uid: str
    entries: dict[str, CoreMemoryEntry] = field(default_factory=dict)


class CoreMemoryStore:
    """按 uid 隔离的 Core Memory 文件存储。"""

    def __init__(self, uid: str, base_dir: Path | None = None) -> None:
        self.uid = uid
        self.base_dir = base_dir or DEFAULT_MEMORY_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.base_dir / f"{uid}.json"
        self._doc = self._load()

    def _load(self) -> CoreMemoryDocument:
        if not self._path.exists():
            return CoreMemoryDocument(uid=self.uid)
        data = json.loads(self._path.read_text(encoding="utf-8"))
        entries: dict[str, CoreMemoryEntry] = {}
        for key, item in (data.get("entries") or {}).items():
            entries[key] = CoreMemoryEntry(
                key=key,
                value=item.get("value", ""),
                category=item.get("category", "profile"),
                updated_at=item.get("updated_at", ""),
            )
        return CoreMemoryDocument(uid=self.uid, entries=entries)

    def _save(self) -> None:
        payload = {
            "uid": self.uid,
            "entries": {k: asdict(v) for k, v in self._doc.entries.items()},
        }
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def add(self, key: str, value: str, category: str = "profile") -> str:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return "Error: key 与 value 均不能为空"
        if category not in VALID_CATEGORIES:
            return f"Error: category 必须是 {', '.join(sorted(VALID_CATEGORIES))} 之一"
        if key in self._doc.entries:
            return f"Error: key '{key}' 已存在，请使用 core_memory_update"
        self._doc.entries[key] = CoreMemoryEntry(
            key=key, value=value, category=category, updated_at=_now_iso()
        )
        self._save()
        return f"Added core memory: {key}"

    def update(self, key: str, value: str, category: str | None = None) -> str:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return "Error: key 与 value 均不能为空"
        entry = self._doc.entries.get(key)
        if not entry:
            return f"Error: key '{key}' 不存在，请使用 core_memory_add"
        entry.value = value
        if category:
            if category not in VALID_CATEGORIES:
                return f"Error: category 必须是 {', '.join(sorted(VALID_CATEGORIES))} 之一"
            entry.category = category
        entry.updated_at = _now_iso()
        self._save()
        return f"Updated core memory: {key}"

    def delete(self, key: str) -> str:
        key = key.strip()
        if key not in self._doc.entries:
            return f"Error: key '{key}' 不存在"
        del self._doc.entries[key]
        self._save()
        return f"Deleted core memory: {key}"

    def list_entries(self) -> list[CoreMemoryEntry]:
        return list(self._doc.entries.values())

    def format_for_prompt(self) -> str:
        """格式化为注入 system prompt 的文本；无条目时返回空串。"""
        from vocamind.memory.prompts import format_core_memory_block

        return format_core_memory_block(self.list_entries())


def get_core_memory_store(uid: str | None, base_dir: Path | None = None) -> CoreMemoryStore:
    key = (uid or "default").strip() or "default"
    with _lock:
        if base_dir is not None:
            return CoreMemoryStore(key, base_dir)
        if key not in _store_cache:
            _store_cache[key] = CoreMemoryStore(key)
        return _store_cache[key]
