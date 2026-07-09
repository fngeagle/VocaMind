"""Session todo 工具。"""
from __future__ import annotations

import ast
import json
from typing import Any

CURRENT_TODOS: list[dict[str, Any]] = []


def _normalize_todos(todos: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todos = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "Error: todos must be a list or JSON array string"
    if not isinstance(todos, list):
        return None, "Error: todos must be a list"
    for i, todo in enumerate(todos):
        if not isinstance(todo, dict):
            return None, f"Error: todos[{i}] must be an object"
        if "content" not in todo or "status" not in todo:
            return None, f"Error: todos[{i}] missing 'content' or 'status'"
        if todo["status"] not in ("pending", "in_progress", "completed"):
            return None, f"Error: todos[{i}] has invalid status '{todo['status']}'"
    return todos, None


def run_todo_write(todos: list[dict[str, Any]]) -> str:
    global CURRENT_TODOS
    normalized, error = _normalize_todos(todos)
    if error:
        return error
    CURRENT_TODOS = normalized or []
    return f"Updated {len(CURRENT_TODOS)} todos"


def get_current_todos() -> list[dict[str, Any]]:
    return list(CURRENT_TODOS)
