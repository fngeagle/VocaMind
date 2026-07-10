"""任务文档产物：登记、查询与安全读取。"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from vocamind.llm.tool_client import parse_tool_arguments

MARKDOWN_SUFFIXES = (".md", ".markdown")
TEXT_SUFFIXES = (".txt",)
HTML_SUFFIXES = (".html", ".htm")
DOCUMENT_SUFFIXES = MARKDOWN_SUFFIXES + TEXT_SUFFIXES + HTML_SUFFIXES


@dataclass
class TaskArtifact:
    task_id: str
    path: str
    title: str
    kind: str  # "markdown" | "html"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _artifact_kind(path: str) -> str | None:
    lower = path.lower()
    if lower.endswith(MARKDOWN_SUFFIXES) or lower.endswith(TEXT_SUFFIXES):
        return "markdown"
    if lower.endswith(HTML_SUFFIXES):
        return "html"
    return None


def _collect_write_paths(messages: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name") != "write_file":
                continue
            try:
                args = parse_tool_arguments(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            path = str(args.get("path") or "").strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def collect_task_artifacts(
    messages: list[dict[str, Any]],
    *,
    task_id: str,
    workdir: Path | None,
) -> list[TaskArtifact]:
    """从 write_file 调用中收集可展示的文档产物。"""
    if not workdir:
        return []

    from vocamind.tools.builtin import safe_path

    artifacts: list[TaskArtifact] = []
    for rel_path in _collect_write_paths(messages):
        kind = _artifact_kind(rel_path)
        if not kind:
            continue
        try:
            if not safe_path(rel_path, workdir).is_file():
                continue
        except ValueError:
            continue
        artifacts.append(
            TaskArtifact(
                task_id=task_id,
                path=rel_path.replace("\\", "/"),
                title=Path(rel_path).name,
                kind=kind,
            )
        )
    return artifacts


class ArtifactRegistry:
    """线程安全的任务文档登记簿。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._workdir: Path | None = None
        self._by_task: dict[str, list[TaskArtifact]] = {}

    def set_workdir(self, workdir: Path) -> None:
        with self._lock:
            self._workdir = workdir

    @property
    def workdir(self) -> Path | None:
        with self._lock:
            return self._workdir

    def register(self, task_id: str, artifacts: list[TaskArtifact]) -> None:
        if not artifacts:
            return
        with self._lock:
            self._by_task[task_id] = list(artifacts)

    def get(self, task_id: str) -> list[TaskArtifact]:
        with self._lock:
            return list(self._by_task.get(task_id, []))

    def resolve_file(self, task_id: str, rel_path: str) -> Path:
        from vocamind.tools.builtin import safe_path

        with self._lock:
            if self._workdir is None:
                raise FileNotFoundError("workdir not configured")
            workdir = self._workdir
            registered = {a.path for a in self._by_task.get(task_id, [])}

        normalized = rel_path.replace("\\", "/").lstrip("/")
        if normalized not in registered:
            raise PermissionError(f"artifact not registered: {task_id}/{normalized}")

        fp = safe_path(normalized, workdir)
        if not fp.is_file():
            raise FileNotFoundError(normalized)
        return fp


_registry = ArtifactRegistry()


def get_artifact_registry() -> ArtifactRegistry:
    return _registry
