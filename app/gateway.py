from __future__ import annotations

import asyncio
import math
import os
from time import monotonic
from pathlib import Path
from urllib.parse import urljoin

import cv2
import httpx
import numpy as np


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
    "16fps-portrait-480x800": (480, 800, 16, 81),
    "16fps-portrait-480x800-startup": (352, 576, 16, 81),
    "16fps-800x480": (800, 480, 16, 81),
    "16fps-800x480-startup": (576, 352, 16, 81),
    "16fps-672x416": (672, 416, 16, 81),
    "16fps-672x416-startup": (512, 320, 16, 81),
    "16fps-704x416": (704, 416, 16, 81),
    "16fps-704x416-startup": (544, 320, 16, 81),
    "16fps-640x480": (640, 480, 16, 81),
    "16fps-640x480-startup": (384, 288, 16, 81),
    "20fps-4x3-balanced": (512, 384, 20, 97),
    "20fps-4x3-balanced-startup": (384, 288, 20, 97),
    "20fps-portrait-416x704": (416, 704, 20, 97),
    "20fps-portrait-416x704-startup": (320, 544, 20, 97),
    "20fps-portrait-480x640": (480, 640, 20, 97),
    "20fps-portrait-480x640-startup": (288, 384, 20, 97),
    "20fps-704x416": (704, 416, 20, 97),
    "20fps-704x416-startup": (544, 320, 20, 97),
    "20fps-640x480": (640, 480, 20, 97),
    "20fps-640x480-startup": (384, 288, 20, 97),
    "24fps-3x2": (480, 320, 24, 121),
    "24fps-3x2-startup": (384, 256, 24, 121),
    "24fps-portrait": (288, 512, 24, 121),
    "24fps-portrait-startup": (256, 448, 24, 121),
    "24fps-portrait-384x640": (384, 640, 24, 121),
    "24fps-portrait-384x640-startup": (288, 480, 24, 121),
    "24fps-portrait-416x704": (416, 704, 24, 121),
    "24fps-portrait-416x704-startup": (320, 544, 24, 121),
    "24fps-640x384": (640, 384, 24, 121),
    "24fps-640x384-startup": (480, 288, 24, 121),
    "24fps-704x416": (704, 416, 24, 121),
    "24fps-704x416-startup": (544, 320, 24, 121),
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
    "16fps-portrait-480x800": "16fps-portrait-480x800-startup",
    "16fps-800x480": "16fps-800x480-startup",
    "16fps-672x416": "16fps-672x416-startup",
    "16fps-704x416": "16fps-704x416-startup",
    "16fps-640x480": "16fps-640x480-startup",
    "20fps-4x3-balanced": "20fps-4x3-balanced-startup",
    "20fps-portrait-416x704": "20fps-portrait-416x704-startup",
    "20fps-portrait-480x640": "20fps-portrait-480x640-startup",
    "20fps-704x416": "20fps-704x416-startup",
    "20fps-640x480": "20fps-640x480-startup",
    "24fps-portrait-384x640": "24fps-portrait-384x640-startup",
    "24fps-portrait-416x704": "24fps-portrait-416x704-startup",
    "24fps-640x384": "24fps-640x384-startup",
    "24fps-704x416": "24fps-704x416-startup",
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
    # リアルタイム優先リースを宣言するバックエンド名(gateway は「他バックエンド」の
    # 生成を入口で 409 にする)。H3 クライアントは "h3" に差し替える。
    lease_backend = "ltx25"

    def __init__(self, base_url: str, preset: str, poll_interval: float = 0.1):
        self.base_url = base_url.rstrip("/")
        self.preset = preset
        self.poll_interval = poll_interval
        self.last_job_id: str | None = None
        self.cancel_requested = False

    # -- リアルタイム優先リース(会話セッション宣言) --------------------------
    # 会話ターンの間これを保持すると、gateway は他バックエンド(H3)の生成・load・
    # unload を入口で 409 にする。H3 の t2va は約25秒かかり途中で止められないため、
    # ターン開始「前」に宣言しておかないと LTX の 4.8 秒予算が守れない。
    # 全て最善努力: リース API が無い古い gateway でも会話は普通に動く
    # (その場合は先に始まった生成が勝つ、従来の挙動に戻るだけ)。

    async def acquire_lease(self, lease_id: str | None = None,
                            ttl_s: float = 60.0) -> str | None:
        """リースを取得(lease_id 指定時は延長)。返り値は現在の lease_id。

        他ターンが release した直後の renew は新しいリースとして受理されるため、
        呼び出し側は**返ってきた id で保持中の id を更新する**こと。
        """
        body: dict = {"backend": self.lease_backend, "ttl_s": ttl_s}
        if lease_id:
            body["lease_id"] = lease_id
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/realtime/lease", json=body)
            if response.is_error:
                return None
            return response.json().get("lease_id")
        except httpx.HTTPError:
            return None

    async def release_lease(self, lease_id: str | None) -> None:
        if not lease_id:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.delete(
                    f"{self.base_url}/api/v1/realtime/lease",
                    params={"lease_id": lease_id})
        except httpx.HTTPError:
            pass  # TTL が安全網なので、解放漏れでも最大60秒で自動失効する

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
        """Load the configured LTX backend early; an identical active setup is a no-op.

        `strategy="coresident"` keeps any other backend (H3) loaded instead of evicting
        it. Without this the gateway defaults to `"process"`, which stops H3 and
        restarts LTX — we only need LTX's weights resident, not the GPU to ourselves.
        Generation stays serialised by the gateway's own execution gate.
        """
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/backend/load",
                json={"backend": "ltx25", "preset": self.preset,
                      "strategy": "coresident"},
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
                       video_profile: str = "20fps-4x3-balanced", steps: int = 8,
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


# ---------------------------------------------------------------------------
# MiniMax-H3 エンジン(docs/h3-engine-plan.md)
#
# 既定の動画エンジンは LTX-2.5 のまま(上のコードは一切変更しない)。H3 は
# セッション単位で選び、以下の定数・関数・クライアントだけが関与する。
# ---------------------------------------------------------------------------

ENGINES = ("ltx25", "h3")

H3_FPS = 24                 # runner 定数(24fps 固定)。LTX の 16/20fps は使えない
H3_MAX_SECONDS = 15.0       # サーバ側の上限(core/runner.py MAX_SECONDS)
# ref2va の参照画像短辺。小さいほど denoise が短い(2026-10-07 実測、同一seed・384×512・
# 73f: 2048=denoise 6.0s / 1024=2.5s / 768=2.0s。品質は3条件とも同一性維持・768が最シャープ)。
# ユーザー目視でも差なしと判定され 768 を既定採用(同日)。env で上書き可。
H3_REFERENCE_SHORT_EDGE = int(os.getenv("H3_REFERENCE_SHORT_EDGE", "768"))
H3_STEPS = 4

# H3 専用の解像度プロファイル(プラン §3b)。32の倍数。リアルタイム成立は画素予算で
# 決まる(~215k px = 32GB級、~246k px = 96GB級)。横型・4:3 系は縦型からの外挿で
# 要1回確認(プラン記載)。値は (width, height)。
H3_PROFILES: dict[str, tuple[int, int]] = {
    "h3-portrait-352x608": (352, 608),      # 32GB級 縦(検証済み)
    "h3-landscape-608x352": (608, 352),     # 32GB級 横(外挿)
    "h3-4x3-512x384": (512, 384),           # 32GB級 4:3(外挿)
    "h3-3x4-384x512": (384, 512),           # 32GB級 3:4(外挿)
    # 長辺512 の1ランク下(2026-10-07 追加、ユーザー要望「素材によっては使える」)。
    # 32の倍数の制約上、正確な3:4は組めないため 5:7(320×448、ほぼ3:4)にした
    # (336×448 指定はバックエンドが 320×448 へ丸めることを実機確認済み)。
    # 実測(同一seed・SE=768・73f): denoise 1.6s / 合計 3.2s / peak 47.6GB。
    "h3-landscape-448x320": (448, 320),     # 軽量 横(実測済み縦型の転置)
    "h3-portrait-320x448": (320, 448),      # 軽量 縦(実測済み)
    "h3-portrait-384x704": (384, 704),      # 96GB級 縦(検証済み)
    "h3-landscape-704x384": (704, 384),     # 96GB級 横(外挿)
    "h3-4x3-544x416": (544, 416),           # 96GB級 4:3(外挿)
    "h3-3x4-416x544": (416, 544),           # 96GB級 3:4(外挿)
}
DEFAULT_H3_PROFILE = "h3-portrait-352x608"

# 待機クリップ(fl2va first=last=アンカー)のプロンプト。probe で実績のある文言。
# **変更しないこと**: 2026-10-07 に2回の A/B を実施し、(1) 否定形除去+末尾句強化は
# 閉口アンカー上で 2/3 悪化、(2) 唇が開いたアンカー上で強化3候補(V3句末尾/
# 「唇が触れ合う」具体句/現行+追記)とも現行比で改善なし・1候補は明確な開口が
# 発生。「薄い開きの持続」はアンカー画像の唇そのもの(FLF の端点強制)であり
# プロンプトの管轄外 — 対処は H3_CLOSED_IDLE_ANCHOR=1 か閉口した元画像。
# (2026-10-06: 口閉じ・同一性維持・先頭/末尾がアンカーへ復帰)。
# プロンプト変更は 2026-10-07 の A/B で悪化を確認済み(「改善版」文言は口がむしろ開く)。
# 変更しないこと。口が開く根因はアンカー画像自体の唇なので、アンカー側
# (H3_CLOSED_ANCHOR_*)で解決する。
H3_IDLE_PROMPT = (
    "The person stands calmly, breathing gently, blinking occasionally, "
    "subtle natural idle motion, no talking, mouth closed."
)
H3_IDLE_SECONDS = 5.0

# 閉口アンカー(2026-10-07 実測): 待機 fl2va は first=last=アンカーなので、アンカーの唇が
# 開いていると口が開いたままの待機になる(プロンプトでは勝てない)。無音 ref2va
# (vocal_lock が無音を固定 → 口が閉じる)を 1 本生成し、その t≈1.0s のフレームを新アンカー
# にすると 4 seed 中 3 つが全フレーム完全閉口になった。この 1 本は ref2va スタックの
# プリワーム(compile + prefix/latent キャッシュ)も兼ねる。
H3_CLOSED_ANCHOR_PROMPT = (
    "The person in the reference image stands calmly facing the camera, relaxed, "
    "lips gently closed."
)
H3_CLOSED_ANCHOR_SECONDS = 3.0
H3_CLOSED_ANCHOR_FRAME_S = 1.0


def normalize_engine(value: str | None, default: str = "ltx25") -> str:
    """Return a supported engine name (unknown values fall back to the default)."""
    candidate = (value or "").strip().lower()
    return candidate if candidate in ENGINES else default


def h3_profile_size(profile: str) -> tuple[int, int]:
    """(width, height) of an H3 profile; unknown keys fall back to the default."""
    return H3_PROFILES.get(profile, H3_PROFILES[DEFAULT_H3_PROFILE])


def h3_num_frames(seconds: float, min_seconds: float = 3.0) -> int:
    """Frame count for a clip that is never shorter than `seconds` (17n+5 grid).

    The server does clamp to [min, 15s] -> round(seconds*24) -> step up to the next
    17n+5 (backends/minimax-h3/core/runner.py `seconds_to_num_frames()`). `round`
    can fall up to half a frame short of the speech, so this uses ceil; sending
    n/24 as `seconds` makes the server's round() reproduce exactly n.
    """
    clamped = max(min_seconds, min(H3_MAX_SECONDS, float(seconds)))
    # 0.02 frame tolerance: durations are stored rounded to 1 ms (<= 0.012 frame), and a
    # clip that lands exactly on a grid point must not be bumped to the next grid.
    frames = math.ceil(clamped * H3_FPS - 0.02)
    while frames % 17 != 5:
        frames += 1
    return frames


def h3_clip_seconds(seconds: float, min_seconds: float = 3.0) -> float:
    """Playback length of the clip the H3 server will generate for `seconds`."""
    return h3_num_frames(seconds, min_seconds) / H3_FPS


def _read_bgr(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise GatewayError(f"画像を読み込めません: {path}")
    return image


def _write_png(path: Path, image: np.ndarray) -> None:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise GatewayError(f"画像を書き出せません: {path}")
    encoded.tofile(str(path))


def image_size(path: Path) -> tuple[int, int]:
    """(width, height) of an image file."""
    height, width = _read_bgr(path).shape[:2]
    return width, height


def cover_crop(source: Path, target: Path, width: int, height: int) -> Path:
    """Resize-to-cover then center-crop to exactly width x height, saved as PNG.

    fl2va treats `image` (first) and `last_image` differently (stretch vs
    cover-crop), so a loopable first=last clip needs both frames pre-fitted to
    the canvas — then both preprocessing paths are the identity (プラン §3).
    """
    image = _read_bgr(source)
    src_h, src_w = image.shape[:2]
    scale = max(width / src_w, height / src_h)
    new_w = max(width, round(src_w * scale))
    new_h = max(height, round(src_h * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LANCZOS4
    resized = cv2.resize(image, (new_w, new_h), interpolation=interpolation)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    _write_png(target, resized[top:top + height, left:left + width])
    return target


def crop_to_aspect(source: Path, target: Path, width: int, height: int) -> Path:
    """Center-crop to the canvas aspect ratio at native resolution (no resize).

    Used for the ref2va speaking anchor: the framing matches the idle clips
    while the server still gets full resolution (it normalises the short edge
    itself via reference_image_short_edge).
    """
    image = _read_bgr(source)
    src_h, src_w = image.shape[:2]
    target_ratio = width / height
    if src_w / src_h > target_ratio:
        new_w, new_h = round(src_h * target_ratio), src_h
    else:
        new_w, new_h = src_w, round(src_w / target_ratio)
    left = (src_w - new_w) // 2
    top = (src_h - new_h) // 2
    _write_png(target, image[top:top + new_h, left:left + new_w])
    return target


class H3GatewayClient(GatewayClient):
    """MiniMax-H3 adapter behind the same gateway (backend="h3").

    Differences from the LTX client that matter (all measured, プラン §4-1):
    - Generation is submit() + wait(), not one blocking call. submit() returns
      only after the job is confirmed running at the backend: a 202 means the
      gateway accepted it, not that the backend started it, and a follow-up job
      submitted in that window is rejected by the backend (409 -> failed).
    - wait() uses the job *status* only. /api/progress is a global singleton the
      gateway cannot attribute to a job (values go backwards while a previous
      clip decodes), so progress values are never used for buffer maths.
    - interrupt hits /h3/api/interrupt without a job id (stops whatever is in
      its denoise phase).
    - load_backend starts the process only; weights load on the first request.
    """

    engine = "h3"
    lease_backend = "h3"

    def __init__(self, base_url: str, preset: str, poll_interval: float = 0.1, *,
                 gpus: str = "0,1", min_seconds: float = 3.0,
                 extra_overrides: dict[str, str] | None = None,
                 submit_deadline_s: float = 120.0, start_timeout_s: float = 240.0,
                 reference_short_edge: int = H3_REFERENCE_SHORT_EDGE):
        super().__init__(base_url, preset, poll_interval)
        self.gpus = gpus
        self.min_seconds = min_seconds
        self.extra_overrides = dict(extra_overrides or {})
        self.submit_deadline_s = submit_deadline_s
        self.start_timeout_s = start_timeout_s
        self.reference_short_edge = reference_short_edge
        self.last_submit_retries = 0

    # -- request builders (pure; unit-tested) ---------------------------------

    def load_body(self) -> dict:
        overrides = {"H3_MIN_SECONDS": f"{self.min_seconds:.1f}"}
        overrides.update(self.extra_overrides)
        return {"backend": "h3", "preset": self.preset, "gpus": self.gpus,
                "toggles": {"turbo": True}, "overrides": overrides}

    def chunk_body(self, *, anchor_id: str, audio_id: str, prompt: str, width: int,
                   height: int, seconds: float, seed: int, steps: int = H3_STEPS) -> dict:
        """Speaking chunk: ref2va, references = [anchor image, chunk wav] in this order."""
        return {
            "backend": "h3", "mode": "ref2v",
            "params": {"prompt": prompt, "width": width, "height": height,
                       "seconds": seconds, "steps": steps, "seed": seed},
            "extra": {"reference_image_short_edge": self.reference_short_edge,
                      "vocal_lock": True},
            "asset_ids": [anchor_id, audio_id],
            "auto_load": False,
        }

    def closed_anchor_body(self, *, anchor_id: str, audio_id: str, width: int, height: int,
                           seed: int) -> dict:
        """Silent ref2va whose t=1.0 s frame becomes the closed-mouth idle anchor.

        Same request shape as a speaking chunk (so it doubles as the ref2va warm-up and
        primes the same reference caches), with a silent wav and the closed-lips prompt.
        """
        return self.chunk_body(
            anchor_id=anchor_id, audio_id=audio_id, prompt=H3_CLOSED_ANCHOR_PROMPT,
            width=width, height=height,
            seconds=h3_clip_seconds(H3_CLOSED_ANCHOR_SECONDS, self.min_seconds), seed=seed)

    def idle_body(self, *, image_id: str, width: int, height: int, seed: int,
                  prompt: str = H3_IDLE_PROMPT, seconds: float = H3_IDLE_SECONDS) -> dict:
        """Idle clip: fl2va with first = last = the canvas-fitted anchor, muted."""
        return {
            "backend": "h3", "mode": "flf2v",
            "params": {"prompt": prompt, "width": width, "height": height,
                       "seconds": seconds, "seed": seed},
            "extra": {"mute": True, "turbo": True},
            "asset_ids": [image_id, image_id],
            "auto_load": False,
        }

    # -- backend lifecycle -----------------------------------------------------

    async def load_backend(self) -> dict:
        """Start the H3 process (weights load lazily on the first generation).

        エンジン切替の瞬間に LTX がまだ生成中(直前セッションの待機補充など)だと
        gateway が 409「バックエンド ltx25 が生成中(busy)」を返す(2026-10-06 実機)。
        LTX の 1 クリップは数十秒で終わるので、409 の間は 2 秒間隔で再試行する。
        """
        deadline = monotonic() + 180.0
        while True:
            async with httpx.AsyncClient(timeout=660) as client:
                response = await client.post(f"{self.base_url}/api/v1/backend/load",
                                             json=self.load_body())
            if response.status_code == 409 and monotonic() < deadline:
                await asyncio.sleep(2.0)
                continue
            break
        if response.is_error:
            raise GatewayError(
                f"H3エンジン準備失敗 HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    async def _post_interrupt(self) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                # job_id 省略 = いま denoise 中のものを止める(プラン C-4)
                await client.post(f"{self.base_url}/h3/api/interrupt", json={})
            except httpx.HTTPError:
                pass  # 中断は最善努力

    # -- generation --------------------------------------------------------------

    async def submit(self, body: dict) -> str:
        """Submit a job and return its id once it is running at the backend."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.submit_deadline_s
        self.last_job_id = None
        self.last_submit_retries = 0
        async with httpx.AsyncClient(timeout=180) as client:
            while True:
                if self.cancel_requested:
                    raise GatewayError("動画生成がinterruptedになりました(送信前に中断)")
                response = await client.post(f"{self.base_url}/api/v1/generate", json=body)
                # 409 = backend busy (previous denoise still running) / not yet loaded.
                if response.status_code == 409 and loop.time() < deadline:
                    self.last_submit_retries += 1
                    await asyncio.sleep(0.1)
                    continue
                if response.is_error:
                    raise GatewayError(
                        f"動画生成受付失敗 HTTP {response.status_code}: {response.text[:800]}")
                break
            job_id = response.json()["id"]
            self.last_job_id = job_id
            if self.cancel_requested:
                await self._post_interrupt()
            await self._wait_started(client, job_id)
        return job_id

    async def _wait_started(self, client: httpx.AsyncClient, job_id: str) -> None:
        """Block until the backend holds its generation lock (job really started).

        The gateway only sees "busy" through the backend's own lock, so a freshly
        accepted job is invisible for a few ms. Submitting the next job before
        this flips is what produced the 409 -> failed jobs in the cadence tests.
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.start_timeout_s
        while True:
            try:
                status = await client.get(f"{self.base_url}/h3/api/status")
                if status.is_success and status.json().get("busy"):
                    return
                job = await client.get(f"{self.base_url}/api/v1/jobs/{job_id}")
                if job.is_success and job.json().get("status") in {
                        "completed", "failed", "interrupted", "cancelled"}:
                    return  # finished (or died) before we saw busy; wait() reports it
            except (httpx.HTTPError, ValueError):
                pass
            if loop.time() > deadline:
                raise GatewayError("H3ジョブがバックエンドで開始されませんでした(タイムアウト)")
            await asyncio.sleep(0.02)

    async def wait(self, job_id: str) -> dict:
        """Poll the job status until completed. Progress values are ignored."""
        async with httpx.AsyncClient(timeout=180) as client:
            while True:
                await asyncio.sleep(self.poll_interval)
                response = await client.get(f"{self.base_url}/api/v1/jobs/{job_id}")
                response.raise_for_status()
                state = response.json()
                if state["status"] == "completed":
                    return state
                if state["status"] == "interrupted":
                    raise GatewayError(
                        f"動画生成がinterruptedになりました: {state.get('error') or ''}")
                if state["status"] in {"failed", "cancelled"}:
                    raise GatewayError(state.get("error") or f"動画生成が{state['status']}になりました")

    @staticmethod
    def is_busy_failure(exc: Exception) -> bool:
        """gateway 受理(202)後にバックエンドの 409 でジョブが failed になったか。

        gateway の受理はバックエンド着手を保証しない(受理〜着手の数ms〜の窓)。
        通常は _wait_started の連鎖で自分のジョブ同士は衝突しないが、**別セッションの
        待機補充**とはこの窓で衝突しうる(2026-10-07 実機: 旧セッションの補充中に
        新規登録の閉口アンカー生成が 202→backend 409→failed→502 になった)。"""
        msg = str(exc)
        return "409" in msg and ("生成が進行中" in msg or "busy" in msg)

    async def generate_blocking(self, body: dict) -> dict:
        """submit() + wait() for callers that do not pipeline (idle clips, prewarm).

        busy 起因の failed(上記の受理後レース)は締切まで再投入する。"""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.submit_deadline_s
        while True:
            try:
                return await self.wait(await self.submit(body))
            except GatewayError as exc:
                if self.is_busy_failure(exc) and loop.time() < deadline and not self.cancel_requested:
                    await asyncio.sleep(0.5)
                    continue
                raise


def make_gateway(engine: str, settings) -> GatewayClient:
    """Engine factory. ltx25 returns exactly the pre-existing client."""
    if normalize_engine(engine) == "h3":
        return H3GatewayClient(settings.gateway_url, settings.h3_gateway_preset,
                               settings.poll_interval, gpus=settings.h3_gpus)
    return GatewayClient(settings.gateway_url, settings.gateway_preset, settings.poll_interval)


