"""MiniMax-H3 engine adapter (docs/h3-engine-plan.md). No GPU / gateway needed."""
import asyncio
import json
from pathlib import Path

import cv2
import httpx
import numpy as np

from app.config import Settings
from app.gateway import (
    GatewayClient, H3GatewayClient, H3_PROFILES, cover_crop, crop_to_aspect,
    h3_clip_seconds, h3_num_frames, make_gateway, normalize_engine,
)
from app.models import NarrationSession
from app.orchestrator import Orchestrator


def test_default_engine_is_ltx_and_everything_else_is_untouched():
    assert Settings().video_engine == "ltx25"
    assert NarrationSession(text="", voice_id=1).video_engine == "ltx25"
    assert normalize_engine(None) == "ltx25" and normalize_engine("bogus") == "ltx25"
    client = make_gateway("ltx25", Settings())
    assert type(client) is GatewayClient          # not the H3 subclass
    assert client.lease_backend == "ltx25"
    assert type(make_gateway("h3", Settings())) is H3GatewayClient
    assert H3GatewayClient.lease_backend == "h3"


def test_h3_profiles_are_24fps_grid_friendly():
    assert H3_PROFILES["h3-portrait-352x608"] == (352, 608)
    assert H3_PROFILES["h3-portrait-384x704"] == (384, 704)
    assert all(w % 32 == 0 and h % 32 == 0 for w, h in H3_PROFILES.values())


def test_h3_frame_grid_matches_the_server_rounding():
    # 17n+5 grid: 3.04 / 4.46 / 5.875 / 7.29 s
    assert [h3_num_frames(s) for s in (0.5, 3.0, 4.4, 5.8, 7.0)] == [73, 73, 107, 141, 175]
    assert h3_clip_seconds(3.0) == 73 / 24
    # a duration already on the grid (stored rounded to 1 ms) stays on it
    assert [h3_num_frames(round(n / 24, 3)) for n in (73, 107, 141, 175)] == [73, 107, 141, 175]
    assert h3_clip_seconds(100.0) == h3_num_frames(15.0) / 24   # clamped at 15s
    # the clip is never shorter than the speech it carries (up to the 15 s cap)
    for speech in (0.2, 2.9, 3.05, 4.5, 5.79, 7.2, 14.9):
        assert h3_clip_seconds(speech) >= speech


def test_load_request_is_process_only_with_turbo_and_min_seconds():
    client = H3GatewayClient("http://gw", "dual-realtime-ref2va", gpus="0,1",
                             extra_overrides={"H3_PORT": "8661"})
    assert client.load_body() == {
        "backend": "h3", "preset": "dual-realtime-ref2va", "gpus": "0,1",
        "toggles": {"turbo": True},
        "overrides": {"H3_MIN_SECONDS": "3.0", "H3_PORT": "8661"},
    }


def test_chunk_and_idle_requests():
    client = H3GatewayClient("http://gw", "p")
    chunk = client.chunk_body(anchor_id="img", audio_id="wav", prompt="p", width=352,
                              height=608, seconds=73 / 24, seed=7)
    assert chunk["mode"] == "ref2v" and chunk["asset_ids"] == ["img", "wav"]
    assert chunk["params"]["steps"] == 4 and chunk["auto_load"] is False
    assert chunk["extra"] == {"reference_image_short_edge": 1024, "vocal_lock": True}
    idle = client.idle_body(image_id="img", width=352, height=608, seed=1)
    assert idle["mode"] == "flf2v" and idle["asset_ids"] == ["img", "img"]
    assert idle["extra"]["mute"] is True and idle["params"]["seconds"] == 5.0
    assert "mouth closed" in idle["params"]["prompt"]


def test_anchor_cover_crop_hits_the_canvas_exactly_and_keeps_the_centre(tmp_path):
    source = np.zeros((960, 640, 3), np.uint8)           # 2:3 portrait
    source[400:560, 240:400] = (0, 0, 255)               # red block in the centre (BGR)
    path = tmp_path / "src.png"
    cv2.imwrite(str(path), source)
    for width, height in ((352, 608), (608, 352), (512, 384)):
        out = cover_crop(path, tmp_path / f"c{width}.png", width, height)
        image = cv2.imread(str(out))
        assert image.shape[:2] == (height, width)
        assert tuple(image[height // 2, width // 2]) == (0, 0, 255)
    # the speaking anchor keeps native resolution and only matches the aspect ratio
    cropped = cv2.imread(str(crop_to_aspect(path, tmp_path / "a.png", 352, 608)))
    assert abs(cropped.shape[1] / cropped.shape[0] - 352 / 608) < 0.005
    assert cropped.shape[1] == 640 or cropped.shape[0] == 960


class FakeBackend:
    """Gateway + H3 backend stand-in that records the order of events."""

    def __init__(self, busy_after_polls: int, conflicts: int):
        self.events: list[str] = []
        self.status_polls = 0
        self.busy_after_polls = busy_after_polls
        self.conflicts = conflicts

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/generate":
            if self.conflicts > 0:
                self.conflicts -= 1
                self.events.append("409")
                return httpx.Response(409, json={"detail": "busy"})
            self.events.append("202")
            return httpx.Response(202, json={"id": "job1", "status": "running"})
        if path == "/h3/api/status":
            self.status_polls += 1
            busy = self.status_polls > self.busy_after_polls
            if busy:
                self.events.append("busy")
            return httpx.Response(200, json={"busy": busy})
        if path == "/api/v1/jobs/job1":
            return httpx.Response(200, json={"id": "job1", "status": "running", "progress": 0.0})
        if path == "/h3/api/interrupt":
            self.events.append("interrupt:" + request.content.decode())
            return httpx.Response(200, json={"interrupted": True})
        raise AssertionError(path)


def patch_httpx(monkeypatch, backend: FakeBackend) -> None:
    real = httpx.AsyncClient
    transport = httpx.MockTransport(backend.handler)
    monkeypatch.setattr("app.gateway.httpx.AsyncClient",
                        lambda **kw: real(transport=transport, **kw))


def test_submit_returns_only_after_the_backend_started_the_job(monkeypatch):
    backend = FakeBackend(busy_after_polls=3, conflicts=2)
    patch_httpx(monkeypatch, backend)
    client = H3GatewayClient("http://gw", "p", poll_interval=0.01)
    job_id = asyncio.run(client.submit({"backend": "h3"}))
    assert job_id == "job1" and client.last_job_id == "job1"
    assert client.last_submit_retries == 2                   # 409 retried until accepted
    assert backend.events == ["409", "409", "202", "busy"]   # 202 never repeated
    assert backend.status_polls == 4                         # waited for busy=true


def test_interrupt_has_no_job_id_and_cancels_before_submission(monkeypatch):
    backend = FakeBackend(busy_after_polls=0, conflicts=0)
    patch_httpx(monkeypatch, backend)
    client = H3GatewayClient("http://gw", "p")
    asyncio.run(client.interrupt())
    assert backend.events == ["interrupt:{}"]
    try:
        asyncio.run(client.submit({"backend": "h3"}))
    except Exception as exc:
        assert "interrupted" in str(exc)
    else:
        raise AssertionError("submit after interrupt must abort")


def test_wait_uses_status_only_and_reports_interrupted(monkeypatch):
    states = iter([{"status": "running", "progress": 0.95},
                   {"status": "running", "progress": 0.05},      # misattributed progress
                   {"status": "completed", "result": {"video_url": "/h3/outputs/a.mp4"}}])

    def handler(request):
        return httpx.Response(200, json={"id": "j", **next(states)})

    real = httpx.AsyncClient
    monkeypatch.setattr("app.gateway.httpx.AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    client = H3GatewayClient("http://gw", "p", poll_interval=0.001)
    assert asyncio.run(client.wait("j"))["result"]["video_url"] == "/h3/outputs/a.mp4"


def test_h3_prompt_quotes_the_line_and_keeps_ltx_prompt_unchanged():
    prompt = Orchestrator._prompt_h3("こんにちは。", "白いスタジオ", "low", "", "")
    assert "<d>こんにちは。</d>" in prompt and "白いスタジオ" in prompt
    # the LTX prompt builder is untouched
    assert 'says exactly: "おはよう。"' in Orchestrator._prompt("おはよう。", "x")


def test_h3_session_defaults_round_trip_through_json():
    session = NarrationSession(text="", voice_id=1, video_engine="h3",
                               video_profile="h3-portrait-352x608")
    restored = NarrationSession.model_validate_json(session.model_dump_json())
    assert restored.video_engine == "h3"
    legacy = json.loads(session.model_dump_json())
    legacy.pop("video_engine")
    assert NarrationSession.model_validate(legacy).video_engine == "ltx25"


def test_presets_carry_the_engine():
    source = Path("app/main.py").read_text(encoding="utf-8")
    assert '"video_engine", "concept"' in source
    assert 'preset_engine != engine' in source
