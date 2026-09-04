from app.gateway import GatewayClient, VIDEO_PROFILES, generation_profile, profile_duration
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


def test_first_portrait_generation_uses_low_latency_profile():
    assert generation_profile("16fps-portrait-3x4", True) == "16fps-portrait-3x4-fast"
    assert generation_profile("16fps-portrait-3x4", False) == "16fps-portrait-3x4"
    assert generation_profile("20fps-hq", True) == "20fps-hq"


def test_job_polling_is_low_latency_by_default():
    assert Settings().poll_interval == 0.1


def test_gateway_generate_defaults_to_eight_steps():
    assert GatewayClient.generate.__defaults__ == ("20fps-hq", 8, None, None)


def test_video_prompt_contains_exact_spoken_text_and_articulation():
    prompt = Orchestrator._prompt("おはようございます。", "白いスタジオ")
    assert 'says exactly: "おはようございます。"' in prompt
    assert "every spoken syllable" in prompt
    assert "mouth must not remain closed" in prompt
