"""文本回复模式：将 LLM 输出直接转发，不合成音频。"""
from __future__ import annotations

from queue import Queue
from threading import Event
from typing import Any, Dict, Iterator

from vocamind.common.handler import BaseHandler
from vocamind.pipeline.attachments import take_pending_attachments, with_attachments


class PassthroughTTSHandler(BaseHandler):
    """TEXT 模式或 TTS 禁用时的直通节点。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        should_listen: Event,
        pending_attachments: dict[str, list[dict[str, str]]] | None = None,
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out)
        self.should_listen = should_listen
        self.pending_attachments = pending_attachments

    def process(self, inputs: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        llm_sentence = inputs["answer_text"]
        end_flag = inputs["end_flag"]
        uid = inputs.get("uid")
        attachments = take_pending_attachments(self.pending_attachments or {}, uid) if end_flag else None

        if not llm_sentence and end_flag:
            yield with_attachments(
                {
                    "question_text": None,
                    "answer_text": "",
                    "answer_audio": "",
                    "end_flag": True,
                    "user_input_count": inputs["user_input_count"],
                    "uid": uid,
                    "proactive": inputs.get("proactive", False),
                },
                attachments,
            )
            self.should_listen.set()
            return

        yield with_attachments(
            {
                "question_text": inputs.get("question_text"),
                "answer_text": llm_sentence,
                "answer_audio": "",
                "end_flag": end_flag,
                "user_input_count": inputs["user_input_count"],
                "uid": uid,
                "proactive": inputs.get("proactive", False),
            },
            attachments if end_flag else None,
        )
        self.should_listen.set()
