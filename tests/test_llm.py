from app.llm import pop_speakable


def test_stream_chunker_waits_for_sentence_end():
    parts, rest = pop_speakable("これは受信中")
    assert parts == []
    assert rest == "これは受信中"


def test_stream_chunker_emits_complete_sentence():
    parts, rest = pop_speakable("最初の文です。次は受信中")
    assert parts == ["最初の文です。"]
    assert rest == "次は受信中"


def test_stream_chunker_limits_long_output():
    parts, rest = pop_speakable("あ" * 40)
    assert parts == ["あ" * 22]
    assert rest == "あ" * 18


def test_weather_response_is_split_for_low_latency():
    text = ("申し訳ありませんが、私はリアルタイムの天気情報を取得することができません。"
            "お住まいの地域の天気予報を、天気予報サイトなどでご確認いただけますでしょうか。")
    parts, rest = pop_speakable(text, force=True)
    assert parts[0] == "申し訳ありませんが、"
    assert "お住まいの地域の天気予報を、" in parts
    assert max(map(len, parts)) <= 26
    assert rest == ""


def test_stream_chunker_flushes_tail():
    parts, rest = pop_speakable("最後の文", force=True)
    assert parts == ["最後の文"]
    assert rest == ""


def test_stream_chunker_emits_greeting_at_comma():
    parts, rest = pop_speakable("おはようございます、今日はどんな一日")
    assert parts == ["おはようございます、"]
    assert rest == "今日はどんな一日"


def test_stream_chunker_does_not_emit_tiny_comma_fragment():
    parts, rest = pop_speakable("はい、続けます")
    assert parts == []
    assert rest == "はい、続けます"


def test_stream_chunker_keeps_question_ending_together():
    parts, rest = pop_speakable("なにかお手伝いできることはありますか。")
    assert parts == ["なにかお手伝いできることはありますか。"]
    assert rest == ""


def test_stream_chunker_does_not_cut_before_single_character_ending():
    parts, rest = pop_speakable("もう少し詳しく教えていただけますか。")
    assert parts == ["もう少し詳しく教えていただけますか。"]
    assert rest == ""


def test_stream_chunker_keeps_natural_weather_advice_together():
    parts, rest = pop_speakable("最新の天気予報をチェックしてみるといいですよ。")
    assert parts == ["最新の天気予報をチェックしてみるといいですよ。"]
    assert rest == ""


def test_stream_chunker_does_not_split_japanese_verb_inflection():
    text = "五反田で「打ってる」というのが具体的に何を指しているか教えていただけますか。例えば、"
    parts, rest = pop_speakable(text, force=True)
    assert "指" not in parts
    assert parts[0].endswith("指しているか")
    assert parts[1] == "教えていただけますか。"
    assert parts[2] == "例えば、"
    assert rest == ""
