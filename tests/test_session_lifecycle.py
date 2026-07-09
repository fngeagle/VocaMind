"""SessionLifecycle 行为测试。"""
from vocamind.pipeline import SessionLifecycle


def test_signal_connect_clears_flush():
    lifecycle = SessionLifecycle()
    lifecycle.signal_disconnect()
    assert lifecycle.flush_requested.is_set()
    lifecycle.signal_connect()
    assert not lifecycle.flush_requested.is_set()


def test_new_topic_requests_flush():
    lifecycle = SessionLifecycle()
    lifecycle.signal_connect()
    lifecycle.signal_new_topic()
    assert lifecycle.flush_requested.is_set()


def test_cur_conn_end_event_alias():
    lifecycle = SessionLifecycle()
    lifecycle.signal_disconnect()
    assert lifecycle.cur_conn_end_event.is_set()
