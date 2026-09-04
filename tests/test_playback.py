from pathlib import Path


def test_ready_following_video_skips_fixed_clip_silence():
    source = Path("app/static/app.js").read_text()

    assert "advanceAfterSpeech(session.chunks)" in source
    assert 'player.addEventListener("timeupdate"' in source
    assert "player.currentTime < current.speech_duration" in source
    assert 'item.index === playingIndex + 1 && item.status === "playable"' in source
