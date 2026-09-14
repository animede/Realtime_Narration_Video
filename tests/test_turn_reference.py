from pathlib import Path


def test_reference_policy_depends_on_character_mode():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert '"natural": folder / "character-neutral.png"' in source
    assert '"balanced": folder / "character-speaking-balanced.png"' in source
    assert '"medium": folder / "character-speaking-medium.png"' in source
    assert '"medium_strong": folder / "character-speaking-medium-strong.png"' in source
    assert '"strong": folder / "character-speaking.png"' in source
    assert 'reference = photoreal_reference() if session.character_mode == "photoreal"' in source
    assert 'session.character_mode == "standard"' in source
    assert "await self._last_frame(output, chain_path)" in source


def test_first_video_of_each_turn_uses_four_steps():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "min(4, session.video_steps) if first_video_of_turn else session.video_steps" in source
    assert "first_video_of_turn = False" in source


def test_video_steps_and_modality_scale_are_user_configurable():
    from app.models import NarrationSession

    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "if session.modality_scale_enabled" in source
    session = NarrationSession(text="", voice_id=1)
    assert session.video_steps == 4
    assert session.modality_scale_enabled is False


def test_all_turn_videos_use_reliable_articulation_seed():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'actual_seed = session.video_seed if session.character_mode == "photoreal"' in source


def test_photoreal_videos_use_effective_video_modality_scale():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert '"natural", "balanced", "medium", "medium_strong", "strong"' in source
    assert 'chunk.modality_scale = actual_modality_scale' in source
    assert '"audio_guidance_scale"' not in Path("app/gateway.py").read_text(encoding="utf-8")


def test_photoreal_character_preparation_creates_speaking_anchor():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert 'anchor_text = "Ah. Ah. Ah. Ah." if session.conversation_language == "en"' in source
    assert 'folder / "character-speaking.png"' in source
    assert 'folder / "character-speaking-balanced.png"' in source
    assert 'folder / "character-speaking-medium.png"' in source
    assert 'folder / "character-speaking-medium-strong.png"' in source
    assert 'folder / "character-neutral.png"' in source
    assert 'preparation_profile = session.video_profile' in source
    assert 'session.video_seed, preparation_profile, 8, preparation_frames, 1.3' in source
    assert 'folder / "character-speaking.png", 0.75' in source
    assert 'folder / "character-speaking-balanced.png", 0.12' in source
    assert 'folder / "character-speaking-medium.png", 0.33' in source
    assert 'folder / "character-speaking-medium-strong.png", 0.54' in source


def test_character_preparation_creates_idle_loop_for_every_mode():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")

    assert 'folder / f"character-idle-{index:03}.mp4"' in source
    assert 'folder / "character-idle-raw.mp4"' in source
    assert "Seamless idle loop" in source
    assert "_make_seamless_loop" in source
    assert "_concat_clips" in source
    assert "last_image_id=idle_image_id" in source
    assert 'session.idle_liveliness != "calm"' in source
    assert "last_image_id=None if lively else idle_image_id" in source
    assert "if session.camera_lock_enabled" in source
    assert "_lock_camera" in source
    assert "at most one soft, brief blink" in source
    assert "faint mouth-corner micro-movement" in source
    assert "idle_frames = preparation_frames" in source
    assert "loop_seconds = (outbound_end + return_frames - 2) / idle_fps" in source
    assert "_select_bridge" in source
    assert "IDLE_MOTION_PROFILES" in source
    assert '"closeup": 1.0' in source
    assert '"upper_body": 1.0' in source
    assert '"wide": 1.0' in source
    assert "_add_idle_to_pool" in source
    assert "IDLE_POOL_SIZE = 3" in source
    assert "session.idle_video_url" in source
    assert '/api/sessions/{session_id}/idle-video' in main


def test_speaking_anchor_keeps_the_selected_full_resolution():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "preparation_profile = session.video_profile" in source
    assert "generation_profile(session.video_profile, first_video_of_turn)" in source


def test_natural_lip_sync_mode_is_default():
    from app.models import NarrationSession

    assert NarrationSession(text="", voice_id=1).lip_sync_mode == "natural"


def test_wide_idle_motion_profile_is_stable_default():
    from app.models import NarrationSession

    assert NarrationSession(text="", voice_id=1).idle_motion_profile == "wide"
    assert NarrationSession(text="", voice_id=1).idle_liveliness == "lively"
    assert NarrationSession(text="", voice_id=1).camera_lock_enabled is False


def test_reliable_articulation_seed_is_default():
    from app.models import NarrationSession

    assert NarrationSession(text="", voice_id=1).video_seed == 1004


def test_introductory_comma_clause_waits_for_its_continuation():
    source = Path("app/orchestrator.py").read_text(encoding="utf-8")
    assert "first_of_turn and complete_sentence" in source
