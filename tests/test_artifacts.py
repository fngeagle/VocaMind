"""任务文档产物测试。"""
from pathlib import Path

from vocamind.tasks.artifacts import (
    ArtifactRegistry,
    collect_task_artifacts,
)


def test_collect_task_artifacts_md_only(tmp_path: Path):
    report = tmp_path / "reports" / "note.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Title\n\nBody", encoding="utf-8")
    (tmp_path / "data.txt").write_text("plain", encoding="utf-8")

    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "a1",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"reports/note.md","content":"x"}',
                    },
                },
                {
                    "id": "a2",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"data.txt","content":"y"}',
                    },
                },
            ],
        }
    ]
    arts = collect_task_artifacts(messages, task_id="task_1", workdir=tmp_path)
    assert len(arts) == 2
    assert arts[0].path == "reports/note.md"
    assert arts[1].path == "data.txt"


def test_registry_resolve_registered_file(tmp_path: Path):
    fp = tmp_path / "doc.md"
    fp.write_text("hello", encoding="utf-8")
    reg = ArtifactRegistry()
    reg.set_workdir(tmp_path)
    from vocamind.tasks.artifacts import TaskArtifact

    reg.register(
        "task_9",
        [TaskArtifact(task_id="task_9", path="doc.md", title="doc.md", kind="markdown")],
    )
    assert reg.resolve_file("task_9", "doc.md").read_text(encoding="utf-8") == "hello"


def test_registry_rejects_unregistered_path(tmp_path: Path):
    fp = tmp_path / "secret.md"
    fp.write_text("x", encoding="utf-8")
    reg = ArtifactRegistry()
    reg.set_workdir(tmp_path)
    try:
        reg.resolve_file("task_9", "secret.md")
        assert False, "should raise"
    except PermissionError:
        pass
