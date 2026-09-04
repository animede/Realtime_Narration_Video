from app.gateway import STARTUP_PROFILES, GatewayClient, VIDEO_PROFILES, generation_profile, profile_duration
from app.config import Settings
from app.models import NarrationSession
from app.orchestrator import Orchestrator

import asyncio
from pathlib import Path


def test_profiles_match_realtime_video_constraints():
    assert VIDEO_PROFILES["20fps-hq"] == (576, 320, 20, 97)
    assert VIDEO_PROFILES["16fps-portrait"] == (384, 640, 16, 81)
    assert VIDEO_PROFILES["24fps-portrait"] == (288, 512, 24, 121)
    assert VIDEO_PROFILES["16fps-portrait-3x4-fast"] == (288, 384, 16, 81)
    assert all(width % 32 == 0 and height % 32 == 0 for width, height, _, _ in VIDEO_PROFILES.values())


def test_last_frame_is_created_for_short_video(tmp_path):
    source = Path("data/4775598320874813b90462798ac5585b/chunk-000.mp4")
    if not source.is_file():
        return
    target = tmp_path / "last.png"
    asyncio.run(Orchestrator._last_frame(source, target))
    assert target.stat().st_size > 0


def test_low_latency_default_starts_with_one_chunk():
    assert NarrationSession(text="", voice_id=1).startup_buffer_chunks == 1


def test_profiles_produce_full_playback_window():
    assert profile_duration("16fps-portrait-3x4") == 5.0
    assert profile_duration("20fps-hq") == 4.8


def test_first_generation_uses_low_latency_variant_for_every_profile():
    assert set(STARTUP_PROFILES) == {
        "16fps-resolution", "16fps-4x3-resolution", "16fps-5x3", "16fps-3x2",
        "16fps-portrait-3x4", "16fps-portrait", "20fps-hq", "20fps-4x3-balanced",
        "24fps-fast", "24fps-3x2", "24fps-portrait",
    }
    for selected, startup in STARTUP_PROFILES.items():
        selected_width, selected_height, selected_fps, selected_frames = VIDEO_PROFILES[selected]
        startup_width, startup_height, startup_fps, startup_frames = VIDEO_PROFILES[startup]
        assert generation_profile(selected, True) == startup
        assert generation_profile(selected, False) == selected
        assert startup_width >= 256 and startup_height >= 256
        assert startup_width * startup_height < selected_width * selected_height
        assert (startup_fps, startup_frames) == (selected_fps, selected_frames)


def test_every_public_profile_has_a_full_resolution_anchor_profile():
    for selected in STARTUP_PROFILES:
        assert selected in VIDEO_PROFILES
        assert generation_profile(selected, False) == selected


def test_job_polling_is_low_latency_by_default():
    assert Settings().poll_interval == 0.1


def test_gateway_generate_defaults_to_eight_steps():
    assert GatewayClient.generate.__defaults__ == ("20fps-hq", 8, None, None)


def test_video_prompt_contains_exact_spoken_text_and_articulation():
    prompt = Orchestrator._prompt("おはようございます。", "白いスタジオ")
    assert 'says exactly: "おはようございます。"' in prompt
    assert "every spoken syllable" in prompt
    assert "mouth must not remain closed" in prompt
