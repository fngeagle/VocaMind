"""中文句子切分：用于流式 LLM 输出按句送入 TTS。"""
import re
from typing import List, Tuple

_SENTENCE_END = re.compile(r"[。？！；]")


def split_first_sentence(text: str) -> Tuple[str, str]:
    """
    从缓冲区中切出第一句完整句子。
    返回 (完整句, 剩余文本)；若尚无完整句则返回 ("", text)。
    """
    parts = _SENTENCE_END.split(text, maxsplit=1)
    if len(parts) < 2:
        return "", text
    first = parts[0].strip()
    if not first:
        return "", text
    match = _SENTENCE_END.search(text)
    punct = match.group(0) if match else "。"
    sentence = first + punct
    remainder = text[len(sentence):]
    return sentence, remainder


def split_sentences(text: str) -> List[str]:
    """将文本按句末标点切分为句子列表。"""
    raw = _SENTENCE_END.split(text)
    result: List[str] = []
    for i, part in enumerate(raw):
        if not part.strip():
            continue
        if i < len(raw) - 1:
            match_iter = list(_SENTENCE_END.finditer(text))
            punct = match_iter[i].group(0) if i < len(match_iter) else "。"
            result.append(part.strip() + punct)
        else:
            if part.strip():
                result.append(part.strip())
    return result
