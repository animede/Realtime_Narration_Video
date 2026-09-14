from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urljoin

import httpx


class GatewayError(RuntimeError):
    pass


VIDEO_PROFILES = {
    "16fps-4x3-resolution": (512, 384, 16, 81),
    "16fps-4x3-resolution-startup": (384, 288, 16, 81),
    "16fps-5x3": (640, 384, 16, 81),
    "16fps-5x3-startup": (480, 288, 16, 81),
    "16fps-3x2": (576, 384, 16, 81),
    "16fps-3x2-startup": (480, 320, 16, 81),
    "16fps-portrait-3x4-fast": (288, 384, 16, 81),
    "16fps-portrait-3x4": (384, 512, 16, 81),
    "16fps-portrait": (384, 640, 16, 81),
    "16fps-portrait-startup": (288, 480, 16, 81),
    "16fps-portrait-416x672": (416, 672, 16, 81),
    "16fps-portrait-416x672-startup": (320, 512, 16, 81),
    "16fps-portrait-416x704": (416, 704, 16, 81),
    "16fps-portrait-416x704-startup": (320, 544, 16, 81),
    "16fps-portrait-480x640": (480, 640, 16, 81),
    "16fps-portrait-480x640-startup": (288, 384, 16, 81),
    "16fps-672x416": (672, 416, 16, 81),
    "16fps-672x416-startup": (512, 320, 16, 81),
    "16fps-704x416": (704, 416, 16, 81),
    "16fps-704x416-startup": (544, 320, 16, 81),
    "16fps-640x480": (640, 480, 16, 81),
    "16fps-640x480-startup": (384, 288, 16, 81),
    "20fps-hq": (576, 320, 20, 97),
    "20fps-hq-startup": (480, 256, 20, 97),
    "20fps-4x3-balanced": (512, 384, 20, 97),
    "20fps-4x3-balanced-startup": (384, 288, 20, 97),
    "24fps-fast": (512, 288, 24, 121),
    "24fps-fast-startup": (448, 256, 24, 121),
    "24fps-3x2": (480, 320, 24, 121),
    "24fps-3x2-startup": (384, 256, 24, 121),
    "24fps-portrait": (288, 512, 24, 121),
    "24fps-portrait-startup": (256, 448, 24, 121),
}

STARTUP_PROFILES = {
    "16fps-4x3-resolution": "16fps-4x3-resolution-startup",
    "16fps-5x3": "16fps-5x3-startup",
    "16fps-3x2": "16fps-3x2-startup",
    "16fps-portrait-3x4": "16fps-portrait-3x4-fast",
    "16fps-portrait": "16fps-portrait-startup",
    "16fps-portrait-416x672": "16fps-portrait-416x672-startup",
    "16fps-portrait-416x704": "16fps-portrait-416x704-startup",
    "16fps-portrait-480x640": "16fps-portrait-480x640-startup",
    "16fps-672x416": "16fps-672x416-startup",
    "16fps-704x416": "16fps-704x416-startup",
    "16fps-640x480": "16fps-640x480-startup",
    "20fps-hq": "20fps-hq-startup",
    "20fps-4x3-balanced": "20fps-4x3-balanced-startup",
    "24fps-fast": "24fps-fast-startup",
    "24fps-3x2": "24fps-3x2-startup",
    "24fps-portrait": "24fps-portrait-startup",
}


def generation_profile(selected_profile: str, first_video_of_turn: bool) -> str:
    """Use a low-latency variant for the first clip of every supported profile."""
    if first_video_of_turn:
        return STARTUP_PROFILES.get(selected_profile, selected_profile)
    return selected_profile


def profile_duration(profile: str) -> float:
    _, _, fps, frames = VIDEO_PROFILES[profile]
    return (frames - 1) / fps


class GatewayClient:
    def __init__(self, base_url: str, preset: str, poll_interval: float = 0.1):
        self.base_url = base_url.rstrip("/")
        self.preset = preset
        self.poll_interval = poll_interval
        self.last_job_id: str | None = None
        self.cancel_requested = False

    async def interrupt(self) -> None:
        """Ask the backend to stop this client's in-flight job.

        Also raises a cancel flag so a generate() that has not submitted its
        job yet aborts before submission (ジョブID取得前の競合対策)。Reaction is
        bounded by one denoise step (~0.5s); the polled job then settles into
        "interrupted" and generate() raises GatewayError.
        """
        self.cancel_requested = True
        await self._post_interrupt()

    async def _post_interrupt(self) -> None:
        if not self.last_job_id:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                await client.post(f"{self.base_url}/ltx25/api/interrupt",
                                  json={"job_id": self.last_job_id})
            except httpx.HTTPError:
                pass  # 中断は最善努力 — 失敗しても生成が続くだけ

    async def load_backend(self) -> dict:
        """Load the configured LTX backend early; an identical active setup is a no-op."""
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/backend/load",
                json={"backend": "ltx25", "preset": self.preset},
            )
        if response.is_error:
            raise GatewayError(f"動画モデル準備失敗 HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    async def upload(self, path: Path) -> str:
        async with httpx.AsyncClient(timeout=180) as client:
            with path.open("rb") as stream:
                response = await client.post(
                    f"{self.base_url}/api/v1/assets", files={"file": (path.name, stream)}
                )
        if response.is_error:
            raise GatewayError(f"アセット登録失敗 HTTP {response.status_code}: {response.text[:500]}")
        return str(response.json()["id"])

    async def generate(self, image_id: str, audio_id: str, prompt: str, seed: int,
                       video_profile: str = "20fps-hq", steps: int = 8,
                       num_frames: int | None = None,
                       modality_scale: float | None = None,
                       last_image_id: str | None = None,
                       last_image_strength: float | None = None) -> dict:
        width, height, fps, frames = VIDEO_PROFILES[video_profile]
        frames = num_frames or frames
        # A second image asset becomes an index=-1 condition on the gateway:
        # the clip gets anchored to it at the final frame (FLF-style a2v).
        asset_ids = [audio_id, image_id]
        if last_image_id is not None:
            asset_ids.append(last_image_id)
        body = {
            "backend": "ltx25",
            "mode": "a2v",
            "params": {"prompt": prompt, "width": width, "height": height,
                       "num_frames": frames, "fps": fps, "steps": steps,
                       "guidance_scale": 3.0, "seed": seed},
            "asset_ids": asset_ids,
            "extra": {"upscale": False, "decoder": "vae", "audio_start": 0},
            "auto_load": True,
            "preset": self.preset,
        }
        if modality_scale is not None:
            body["extra"]["modality_scale"] = modality_scale
        if last_image_id is not None and last_image_strength is not None:
            # Override the tail anchor only; a full-strength (1.0) end anchor
            # makes the model freeze the whole clip to guarantee the return.
            body["extra"]["conditions"] = [{}, {"strength": last_image_strength}]
        self.last_job_id = None
        async with httpx.AsyncClient(timeout=180) as client:
            # gatewayはバックエンド生成中の新規ジョブを409(busy)で拒否する
            # (キューイング非対応)。アイドル生成の中断完了までの短い窓を
            # リトライで吸収する。
            deadline = asyncio.get_event_loop().time() + 15.0
            while True:
                if self.cancel_requested:
                    raise GatewayError("動画生成がinterruptedになりました(送信前に中断)")
                response = await client.post(f"{self.base_url}/api/v1/generate", json=body)
                if response.status_code == 409 and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.3)
                    continue
                if response.is_error:
                    detail = response.text[:800]
                    raise GatewayError(f"動画生成受付失敗 HTTP {response.status_code}: {detail}")
                break
            job_id = response.json()["id"]
            self.last_job_id = job_id
            if self.cancel_requested:
                await self._post_interrupt()
            while True:
                await asyncio.sleep(self.poll_interval)
                response = await client.get(f"{self.base_url}/api/v1/jobs/{job_id}")
                response.raise_for_status()
                state = response.json()
                if state["status"] == "completed":
                    return state
                if state["status"] in {"failed", "interrupted", "cancelled"}:
                    raise GatewayError(state.get("error") or f"動画生成が{state['status']}になりました")

    async def download(self, relative_url: str, target: Path) -> None:
        url = urljoin(self.base_url + "/", relative_url.lstrip("/"))
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with target.open("wb") as output:
                    async for block in response.aiter_bytes():
                        output.write(block)
