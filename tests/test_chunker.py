from app.chunker import SpeechPart, group_parts, split_sentences


def part(text: str, duration: float) -> SpeechPart:
    return SpeechPart(text, b"wav", duration)


def test_split_sentences_keeps_punctuation():
    assert split_sentences("こんにちは。元気ですか？\nはい！") == ["こんにちは。", "元気ですか？", "はい！"]


def test_long_sentence_is_split():
    chunks = split_sentences("あ" * 100, max_chars=30)
    assert all(len(item) <= 30 for item in chunks)
    assert "".join(chunks) == "あ" * 100


def test_group_parts_uses_spoken_duration():
    groups = group_parts([part("a", 2.0), part("b", 2.1), part("c", 2.0)], target=5.0, maximum=5.0)
    assert [[item.text for item in group] for group in groups] == [["a", "b"], ["c"]]


def test_group_parts_breaks_before_maximum():
    groups = group_parts([part("a", 3.6), part("b", 3.2)], target=5.0, maximum=6.5)
    assert len(groups) == 2
