from pathlib import Path


def test_mux_preserves_the_complete_original_audio():
    muxer = Path("app/muxer.py").read_text(encoding="utf-8")
    orchestrator = Path("app/orchestrator.py").read_text(encoding="utf-8")

    assert '"-t"' not in muxer
    assert "mux_original_audio(raw, audio_path, output)" in orchestrator
    assert "chunk_duration = max(clip_duration, parts_duration)" in orchestrator
