from pathlib import Path


def test_reference_policy_depends_on_character_mode():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'speaking_reference = folder / "character-speaking.png"' in source
    assert 'session.character_mode == "photoreal" or chain_path == reference' in source
    assert 'session.character_mode == "standard"' in source
    assert "await self._last_frame(output, chain_path)" in source


def test_first_video_of_each_turn_uses_four_steps():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "actual_steps = 4 if first_video_of_turn else 8" in source
    assert "first_video_of_turn = False" in source


def test_all_turn_videos_use_reliable_articulation_seed():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'actual_seed = 1004 if session.character_mode == "photoreal" else 1000 + chunk.index' in source


def test_photoreal_videos_use_effective_video_modality_scale():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'session.character_mode == "photoreal" and session.lip_sync_mode == "strong"' in source
    assert 'chunk.modality_scale = actual_modality_scale' in source
    assert '"audio_guidance_scale"' not in Path("app/gateway.py").read_text(encoding="utf-8")


def test_photoreal_character_preparation_creates_speaking_anchor():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'self.settings.tts_url, session.voice_id, "あー、あー、あー、あー。"' in source
    assert 'folder / "character-speaking.png"' in source
    assert 'preparation_profile = session.video_profile' in source
    assert '1004, preparation_profile, 8, preparation_frames, 1.3' in source
    assert 'folder / "character-speaking.png", 0.75' in source


def test_fast_lip_sync_mode_is_default():
    from app.models import NarrationSession

    assert NarrationSession(text="", voice_id=1).lip_sync_mode == "fast"


def test_introductory_comma_clause_waits_for_its_continuation():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "first_of_turn and complete_sentence" in source
