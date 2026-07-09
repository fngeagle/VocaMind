"""LLM 流式推理的单步处理（纯函数）。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

from vocamind.common.sentence import split_first_sentence
from vocamind.llm.stream_state import LLMStreamState


def build_chunk_output(
    *,
    question_text: Optional[str],
    answer_text: str,
    end_flag: bool,
    user_input_count: int,
    uid: str,
    proactive: bool = False,
) -> Dict[str, Union[str, int, bool, None]]:
    return {
        "question_text": question_text,
        "answer_text": answer_text,
        "end_flag": end_flag,
        "user_input_count": user_input_count,
        "uid": uid,
        "proactive": proactive,
    }


def append_stream_delta(state: LLMStreamState, delta: str) -> LLMStreamState:
    return LLMStreamState(
        generated_text=state.generated_text + delta,
        printable_text=state.printable_text + delta,
        sentence_count=state.sentence_count,
        first_token_logged=True,
    )


def extract_ready_sentences(
    state: LLMStreamState,
    *,
    prompt: str,
    audio_input: bool,
    user_input_count: int,
    uid: str,
    proactive: bool = False,
) -> Tuple[LLMStreamState, List[Dict[str, Union[str, int, bool, None]]]]:
    """从缓冲区切出所有完整句子，返回新状态与待 yield 的输出列表。"""
    outputs: List[Dict[str, Union[str, int, bool, None]]] = []
    printable_text = state.printable_text
    sentence_count = state.sentence_count

    while True:
        new_sentence, remainder = split_first_sentence(printable_text)
        if not new_sentence:
            break
        outputs.append(
            build_chunk_output(
                question_text=prompt if audio_input and sentence_count == 0 else None,
                answer_text=new_sentence,
                end_flag=not remainder.strip(),
                user_input_count=user_input_count,
                uid=uid,
                proactive=proactive,
            )
        )
        sentence_count += 1
        printable_text = remainder

    new_state = LLMStreamState(
        generated_text=state.generated_text,
        printable_text=printable_text,
        sentence_count=sentence_count,
        first_token_logged=state.first_token_logged,
    )
    return new_state, outputs


def extract_tail_sentence(
    state: LLMStreamState,
    *,
    prompt: str,
    audio_input: bool,
    user_input_count: int,
    uid: str,
    proactive: bool = False,
) -> Tuple[LLMStreamState, Optional[Dict[str, Union[str, int, bool, None]]]]:
    """流结束后输出未以句末标点结尾的剩余文本。"""
    if not state.printable_text.strip():
        return state, None
    output = build_chunk_output(
        question_text=prompt if audio_input and state.sentence_count == 0 else None,
        answer_text=state.printable_text.strip(),
        end_flag=True,
        user_input_count=user_input_count,
        uid=uid,
        proactive=proactive,
    )
