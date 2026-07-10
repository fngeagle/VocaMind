"""出站文档附件合并测试。"""
from vocamind.pipeline.attachments import take_pending_attachments, with_attachments


def test_take_pending_attachments():
    store = {"u1": [{"task_id": "t1", "path": "a.md"}]}
    got = take_pending_attachments(store, "u1")
    assert got == [{"task_id": "t1", "path": "a.md"}]
    assert store == {}


def test_with_attachments():
    payload = {"end_flag": True, "uid": "u1"}
    merged = with_attachments(payload, [{"task_id": "t1", "path": "a.md"}])
    assert merged["attachments"][0]["path"] == "a.md"
    assert with_attachments(payload, None) is payload
