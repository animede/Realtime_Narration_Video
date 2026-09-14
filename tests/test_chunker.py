from app.chunker import SpeechPart, group_parts, split_sentences


def part(text: str, duration: float) -> SpeechPart:
    return SpeechPart(text, b"wav", duration)


def test_split_sentences_keeps_punctuation():
    assert split_sentences("こんにちは。元気ですか？\nはい！") == ["こんにちは。", "元気ですか？", "はい！"]


def test_long_sentence_is_split_only_at_punctuation():
    text = "ひとつめの節を読み、ふたつめの節も読み、みっつめの節まで読み続けてから終わります"
    chunks = split_sentences(text, max_chars=20)
    # 窓内の最後の読点まで詰めて切る(読点以外では切らない)
    assert chunks == ["ひとつめの節を読み、ふたつめの節も読み、", "みっつめの節まで読み続けてから終わります"]


def test_sentence_without_punctuation_is_never_chopped():
    # 句読点のない位置での文字数ぶち切りはしない(不自然な切れ目対策)。
    assert split_sentences("あ" * 100, max_chars=30) == ["あ" * 100]


def test_group_parts_uses_spoken_duration():
    groups = group_parts([part("a", 2.0), part("b", 2.1), part("c", 2.0)], target=5.0, maximum=5.0)
    assert [[item.text for item in group] for group in groups] == [["a", "b"], ["c"]]


def test_group_parts_breaks_before_maximum():
    groups = group_parts([part("a", 3.6), part("b", 3.2)], target=5.0, maximum=6.5)
    assert len(groups) == 2
