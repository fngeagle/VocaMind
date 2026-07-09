"""文本回复模式：将 LLM 输出直接转发，不合成音频。"""
from __future__ import annotations

from queue import Queue
from threading import Event
from typing import Any, Dict, Iterator

from vocamind.common.handler import BaseHandler


class PassthroughTTSHandler(BaseHandler):
    """TEXT 模式或 TTS 禁用时的直通节点。"""

    def __init__(
        self,
        stop_event: Event,
        cur_conn_end_event: Event,
        queue_in: Queue,
        queue_out: Queue,
        should_listen: Event,
    ) -> None:
        super().__init__(stop_event, cur_conn_end_event, queue_in, queue_out)
        self.should_listen = should_listen

    def process(self, inputs: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        llm_sentence = inputs["answer_text"]
        end_flag = inputs["end_flag"]

        if not llm_sentence and end_flag:
            yield {
                "question_text": None,
                "answer_text": "",
                "answer_audio": "",
                "end_flag": True,
                "user_input_count": inputs["user_input_count"],
                "uid": inputs["uid"],
                "proactive": inputs.get("proactive", False),
            }
            self.should_listen.set()
            return

        yield {
            "question_text": inputs.get("question_text"),
            "answer_text": llm_sentence,
            "answer_audio": "",
            "end_flag": end_flag,
            "user_input_count": inputs["user_input_count"],
            "uid": inputs["uid"],
            "proactive": inputs.get("proactive", False),
        }
        self.should_listen.set()
