from app.llm import pop_speakable


def test_stream_chunker_waits_for_sentence_end():
    parts, rest = pop_speakable("これは受信中")
    assert parts == []
    assert rest == "これは受信中"


def test_stream_chunker_emits_complete_sentence():
    parts, rest = pop_speakable("最初の文です。次は受信中")
    assert parts == ["最初の文です。"]
    assert rest == "次は受信中"


def test_stream_chunker_waits_for_punctuation():
    # 句読点が来るまで切らずに待つ(ぶち切り禁止)。強制フラッシュ時のみ全量。
    parts, rest = pop_speakable("あ" * 40)
    assert parts == []
    assert rest == "あ" * 40
    parts, rest = pop_speakable("あ" * 40, force=True)
    assert parts == ["あ" * 40]
    assert rest == ""


def test_weather_response_is_split_for_low_latency():
    text = ("申し訳ありませんが、私はリアルタイムの天気情報を取得することができません。"
            "お住まいの地域の天気予報を、天気予報サイトなどでご確認いただけますでしょうか。")
    parts, rest = pop_speakable(text, force=True)
    assert parts[0] == "申し訳ありませんが、"
    assert "お住まいの地域の天気予報を、" in parts
    assert all(part.endswith(("。", "、")) for part in parts)
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
    assert parts[0].endswith("ますか。")  # 文末までひとまとまり(活用の途中で切らない)
    assert parts[1] == "例えば、"
    assert rest == ""


def test_english_stream_chunker_emits_sentence():
    parts, rest = pop_speakable("Good morning. How can I help", language="en")
    assert parts == ["Good morning."]
    assert rest == "How can I help"


def test_english_stream_chunker_splits_on_word_boundary():
    text = "This is a deliberately long English response that should split cleanly between words while streaming"
    parts, rest = pop_speakable(text, language="en")
    assert parts
    assert parts[0][-1].isalpha()
    assert text.startswith(parts[0])
    assert not rest.startswith(" ")

def test_clause_commas_split_but_enumeration_commas_do_not():
    # 節境界(直前がひらがなの読点)で切り、名詞列挙の読点では切らない
    # (2026-09-14 ユーザー指定の分解粒度)。
    text = ("前者は入力されたパラメータを即座に映像化する能力であり、"
            "後者は発話内容、口調、感情、相手との関係、直前の身体状態などを解釈し、"
            "その場にふさわしい動作系列を新たに構成する能力です。")
    parts, rest = pop_speakable(text, force=True)
    assert parts == [
        "前者は入力されたパラメータを即座に映像化する能力であり、",
        "後者は発話内容、口調、感情、相手との関係、直前の身体状態などを解釈し、",
        "その場にふさわしい動作系列を新たに構成する能力です。",
    ]
    assert rest == ""

def test_headings_newlines_and_short_enumeration_items():
    # 見出しのコロン・改行は区切り。ひらがな終わりでも短い列挙項目
    # (瞬き、)では切らない(直前の区切りから8文字以上の距離条件)。
    text = ("問題の所在：リアルタイム描画とリアルタイム行動は異なる\n"
            "現在のAIキャラクターやAI VTuberの多くは、音声合成、リップシンク、瞬き、"
            "視線制御、表情切り替えなどをリアルタイムに行います。")
    parts, rest = pop_speakable(text, force=True)
    assert parts == [
        "問題の所在：",
        "リアルタイム描画とリアルタイム行動は異なる",
        "現在のAIキャラクターやAI VTuberの多くは、",
        "音声合成、リップシンク、瞬き、視線制御、表情切り替えなどをリアルタイムに行います。",
    ]
    assert rest == ""
