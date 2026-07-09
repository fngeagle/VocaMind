"""句切分工具测试。"""
from vocamind.common.sentence import split_first_sentence, split_sentences


def test_split_first_sentence_with_period():
    sentence, remainder = split_first_sentence("你好。世界")
    assert sentence == "你好。"
    assert remainder == "世界"


def test_split_first_sentence_with_exclamation():
    sentence, remainder = split_first_sentence("太好了！继续")
    assert sentence == "太好了！"
    assert remainder == "继续"


def test_split_first_sentence_incomplete():
    sentence, remainder = split_first_sentence("还没说完")
    assert sentence == ""
    assert remainder == "还没说完"


def test_split_first_sentence_only_one():
    sentence, remainder = split_first_sentence("就一句。")
    assert sentence == "就一句。"
    assert remainder == ""


def test_split_sentences_multiple():
    result = split_sentences("第一句。第二句！第三句")
    assert len(result) >= 2
