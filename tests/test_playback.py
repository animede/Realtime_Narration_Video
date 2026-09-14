from pathlib import Path


def test_audio_end_always_skips_fixed_clip_silence():
    source = Path("app/static/app.js").read_text()

    assert "advanceAfterSpeech(session.chunks)" in source
    assert 'player.addEventListener("timeupdate"' in source
    assert "player.currentTime < current.speech_duration" in source
    assert "showIdleStage();" in source
    assert "deterministically hides any open mouth" in source


def test_generated_idle_video_is_used_between_speech_clips():
    html = Path("app/static/index.html").read_text()
    source = Path("app/static/app.js").read_text()

    assert 'id="stage-idle"' in html
    assert "muted autoplay" in html
    assert 'id="stage-idle-b"' in html
    assert "absorbIdlePool" in source
    assert "maybeExtendIdlePool" in source
    assert "showIdleStage()" in source
    assert "if (playingIndex === null) showIdleStage()" in source
