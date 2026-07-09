"""基础文件与 bash 工具。"""
from __future__ import annotations

import glob as glob_module
import subprocess
from pathlib import Path

from vocamind.common.paths import PROJECT_ROOT

WORKDIR = PROJECT_ROOT


def set_workdir(path: Path) -> None:
    global WORKDIR
    WORKDIR = path


def safe_path(p: str, cwd: Path | None = None) -> Path:
    base = cwd or WORKDIR
    path = (base / p).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(command: str, cwd: Path | None = None, run_in_background: bool = False) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd or WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout + result.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int | None = None, offset: int = 0, cwd: Path | None = None) -> str:
    try:
        lines = safe_path(path, cwd).read_text(encoding="utf-8").splitlines()
        offset = max(int(offset or 0), 0)
        limit_val = int(limit) if limit is not None else None
        lines = lines[offset:]
        if limit_val is not None and limit_val < len(lines):
            lines = lines[:limit_val] + [f"... ({len(lines) - limit_val} more lines)"]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str, cwd: Path | None = None) -> str:
    try:
        fp = safe_path(path, cwd)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str, cwd: Path | None = None) -> str:
    try:
        fp = safe_path(path, cwd)
        text = fp.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        fp.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_glob(pattern: str, cwd: Path | None = None) -> str:
    try:
        base = cwd or WORKDIR
        results = []
        for match in glob_module.glob(pattern, root_dir=base):
            if (base / match).resolve().is_relative_to(base.resolve()):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as exc:
        return f"Error: {exc}"
