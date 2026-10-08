from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from time import time

from .chunker import SpeechPart
from .config import Settings
from .gateway import (
    GatewayError,
    VIDEO_PROFILES, GatewayClient, H3GatewayClient, H3_CLOSED_ANCHOR_FRAME_S, H3_IDLE_PROMPT,
    H3_IDLE_SECONDS, H3_STEPS, cover_crop, crop_to_aspect, generation_profile,
    h3_clip_seconds, h3_profile_size, h3_startup_size, image_size, make_gateway, profile_duration,
)

# H3 の待機プール(fl2va first=last)専用の閉口アンカー。発話側の参照
# (character-neutral.png)とは別物で、無音 ref2va の t=1.0s フレーム(prepare_character
# で生成。プリセットに含まれ、復元時は再生成しない)。
H3_IDLE_ANCHOR_NAME = "character-idle-anchor.png"
from .llm import StreamingChatClient, pop_speakable
from .models import ChatMessage, Chunk, NarrationSession, SessionStatus
from .muxer import mux_original_audio
from .tts import join_wavs, pad_wav, silent_wav, synthesize_sentence

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_JA = (
    "あなたは音声で応答する親切な日本語アシスタントです。質問へ自然な話し言葉で簡潔に答えてください。"
    "Markdown、箇条書き記号、URLの読み上げは避け、一文を短くしてください。"
)

SYSTEM_PROMPT_EN = (
    "You are a helpful English-speaking voice assistant. Answer naturally and concisely in spoken English. "
    "Avoid Markdown, list markers, and reading URLs aloud. Keep each sentence short."
)

SYSTEM_PROMPT_AUTO = (
    "You are a helpful voice assistant. Reply in the same language as the user's latest message, using natural, "
    "concise spoken language. Avoid Markdown, list markers, and reading URLs aloud. Keep each sentence short."
)

ACTION_DIRECTIONS = {
    "low": (
        "Keep the head and body nearly still. Allow only tiny natural blinking and breathing. "
        "No hand gestures, nodding, swaying, broad poses, or exaggerated facial expressions."
    ),
    "medium": (
        "Use restrained, natural head and upper-body movement with occasional small gestures. "
        "Avoid sudden, broad, or exaggerated motion."
    ),
    "high": (
        "Use lively, expressive head and upper-body movement with occasional clear gestures, while keeping "
        "the face and mouth visible and avoiding abrupt or extreme motion."
    ),
}

IDLE_MOTION_PROFILES = {
    # Playback slowdown per composition. The loop spans the full clip: both
    # ends are anchored to the input image (FLF-style a2v conditioning), so
    # the clip is natively loopable and drift is forced to return home.
    # Camera drift is cancelled mechanically (_lock_camera), so play at
    # natural speed — slowing down reads as a lifeless character (2026-09-14
    # 実測: raw動き2.2がスロー1.2-1.4で1.0前後まで目減りして見えた).
    "closeup": 1.0,
    "upper_body": 1.0,
    "wide": 1.0,
}


def system_prompt(language: str) -> str:
    return {"ja": SYSTEM_PROMPT_JA, "en": SYSTEM_PROMPT_EN}.get(language, SYSTEM_PROMPT_AUTO)


class Orchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, NarrationSession] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        # 進行中のアイドル生成のクライアント(チャット到着時に即中断するため)。
        self.idle_clients: dict[str, GatewayClient] = {}
        # H3 のプリワーム(ref2va ダミー1本)のバックグラウンドタスク。
        self.h3_warmups: dict[str, asyncio.Task] = {}
        settings.data_dir.mkdir(parents=True, exist_ok=True)

    def _gateway(self, session: NarrationSession) -> GatewayClient:
        """Gateway client for the session's engine (ltx25 = the original client)."""
        if session.video_engine == "h3":
            return make_gateway("h3", self.settings)
        return GatewayClient(self.settings.gateway_url, self.settings.gateway_preset,
                             self.settings.poll_interval)

    @staticmethod
    def _is_h3(session: NarrationSession) -> bool:
        return session.video_engine == "h3"

    async def interrupt_idle(self, session_id: str) -> None:
        """Stop ALL in-flight idle generations so a conversation can start now.

        単一GPU・gatewayキューイング非対応のため、会話はセッションを問わず
        絶対優先にする(2026-09-14 実測: 別タブの追い生成ペアがターンの
        chunk間に割り込み、409リトライで+3.3秒のギャップを作った)。
        The backend honours the interrupt at the next denoise step boundary
        (~0.5s), freeing the GPU for the first conversational chunk.
        """
        del session_id  # 全セッション一律に中断する
        for client in list(self.idle_clients.values()):
            await client.interrupt()

    def any_conversation_running(self) -> bool:
        return any(not task.done() for task in self.tasks.values())

    def register(self, session: NarrationSession) -> None:
        self.sessions[session.id] = session

    def chat(self, session: NarrationSession, character: Path,
             turn_video_instruction: str = "",
             turn_anchor: Path | None = None) -> None:
        self.sessions[session.id] = session
        self.tasks[session.id] = asyncio.create_task(
            self._run_chat(session, character, turn_video_instruction=turn_video_instruction,
                           turn_anchor=turn_anchor)
        )

    def narrate(self, session: NarrationSession, character: Path, text: str,
                turn_anchor: Path | None = None) -> None:
        """Speak supplied text directly without sending it to the LLM."""
        self.sessions[session.id] = session
        self.tasks[session.id] = asyncio.create_task(
            self._run_chat(session, character, narration_text=text, turn_anchor=turn_anchor)
        )

    def is_running(self, session_id: str) -> bool:
        task = self.tasks.get(session_id)
        return task is not None and not task.done()

    def save(self, session: NarrationSession) -> None:
        session.updated_at = time()
        folder = self.settings.data_dir / session.id
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / "session.json.tmp"
        temporary.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(folder / "session.json")

    async def _build_idle_loop(self, session: NarrationSession, gateway: GatewayClient,
                               folder: Path, character: Path, target: Path,
                               base_seed: int,
                               neutral_target: Path | None = None) -> Path:
        """Generate the idle clip and turn it into the display loop.

        Two liveliness modes (2026-09-14 実測):
        - calm: both ends FLF-anchored to the input image → perfectly seamless
          loop, but the anchor suppresses motion globally (~2.2 → こぢんまり).
        - lively(既定): 往路+復路の2本構成(ユーザー案)。往路は先頭アンカーのみで
          自由に動かし(アンカーを外すと動きが2倍になる。プロンプト・ネガティブ・
          アンカー強度では制御不能と同一seed A/Bで確認済み)、復路は「往路の最終
          フレーム→入力画像」のFLFで元のポーズへ帰す。連結すると入力ポーズで
          始まり入力ポーズで終わるためハードカットもクロスフェードも不要
          (顔ブレンドは顔崩壊するため厳禁)。
        """
        if self._is_h3(session):
            return await self._build_idle_loop_h3(session, gateway, folder, character,
                                                  target, base_seed)
        lively = session.idle_liveliness != "calm"
        preparation_profile = session.video_profile
        _, _, idle_fps, preparation_frames = VIDEO_PROFILES[preparation_profile]
        idle_frames = preparation_frames
        idle_condition = folder / "character-idle.wav"
        idle_seconds = (idle_frames - 1) / idle_fps
        idle_condition.write_bytes(silent_wav(idle_seconds + 0.2))
        idle_image_id, idle_audio_id = await asyncio.gather(
            gateway.upload(character), gateway.upload(idle_condition)
        )
        camera_tail = (
            "No gestures, camera movement, or scene change. Use a completely locked-off camera with "
            "fixed focal length: zero zoom, dolly, reframing, or change in subject scale. "
            "Preserve exact identity and pixel-consistent composition. "
        )
        if lively:
            idle_prompt = (
                "Idle video of the same character waiting in the same scene, full of quiet life. "
                "The lips remain naturally closed with no speaking or mouth articulation. The eyes stay "
                "open almost the whole time; at most one soft, brief blink may occur. Lively natural idle "
                "motion: visible breathing, gentle weight shifts from side to side, small head tilts and "
                "turns, hair swaying as if in a light breeze, softly changing relaxed expression. "
                + camera_tail
            )
        else:
            idle_prompt = (
                "Seamless idle loop of the same character waiting calmly in the same scene. The lips remain "
                "naturally closed with no speaking or mouth articulation. The eyes stay open almost the whole "
                "time; at most one soft, brief blink may occur. Allow subtle breathing and a relaxed expression "
                "with faint mouth-corner micro-movement; the head and body remain nearly still. "
                "No gestures, nodding, swaying, camera "
                "movement, or scene change. Use a completely locked-off camera with "
                "fixed focal length: zero zoom, dolly, reframing, or change in subject scale. Keep a calm, "
                "consistent expression throughout. Preserve exact identity and pixel-consistent composition. "
                "Finish in the same neutral pose as the first frame for a smooth loop."
            )
        idle_raw = folder / "character-idle-raw.mp4"
        # 位置飛び(>5px/フレーム)は生成に焼き込まれるためseedを変えて引き直す。
        # 3回とも不合格なら最も飛びの小さかったものを採用する。
        jump_limit = 5.0
        best_jump = None
        for attempt in range(3):
            idle_result = await gateway.generate(
                idle_image_id, idle_audio_id,
                last_image_id=None if lively else idle_image_id,
                prompt=idle_prompt,
                seed=base_seed + attempt * 101,
                video_profile=preparation_profile,
                steps=8, num_frames=idle_frames,
            )
            candidate = folder / "character-idle-candidate.mp4"
            await gateway.download(idle_result["result"]["video_url"], candidate)
            jump = await asyncio.to_thread(self._max_translation_jump, candidate)
            if best_jump is None or jump < best_jump:
                best_jump = jump
                candidate.replace(idle_raw)
            else:
                candidate.unlink(missing_ok=True)
            if best_jump <= jump_limit:
                break
        return_frames = 0
        outbound_end = idle_frames - 1
        if lively:
            # 復路: 往路から元の入力画像へFLFで帰す(ユーザー案)。橋渡しフレームは
            # 「終盤で最もシャープかつ動きの少ないフレーム」を選ぶ — 最終フレーム
            # 固定だとモーションブラーの乗ったフレームを条件にしてしまい、復路の
            # 画質が一段落ちる(2026-09-14 実測: 接合点以降がソフトに崩れた)。
            bridge = folder / "character-idle-bridge.png"
            outbound_end = await asyncio.to_thread(self._select_bridge, idle_raw, bridge)
            # 復路はゆっくり戻す。短いと引き戻しが急になり位置が飛ぶ
            # (2026-09-14 実測: 9.5px/フレームの瞬間ずれ。通常は0.4px)。
            return_frames = 8 * max(3, round((idle_frames - 1) / 12)) + 1
            return_condition = folder / "character-idle-return.wav"
            return_condition.write_bytes(
                silent_wav((return_frames - 1) / idle_fps + 0.2))
            bridge_id, return_audio_id = await asyncio.gather(
                gateway.upload(bridge), gateway.upload(return_condition)
            )
            return_raw = folder / "character-idle-return.mp4"
            best_jump = None
            for attempt in range(3):
                return_result = await gateway.generate(
                    bridge_id, return_audio_id, last_image_id=idle_image_id,
                    prompt=(
                        "Idle video of the same character in the same scene. The lips remain naturally "
                        "closed with no speaking or mouth articulation; the eyes stay open. The character "
                        "stays almost still, breathing gently, and very slowly and smoothly settles back "
                        "into the original relaxed neutral pose. Every movement is slight, gradual, and "
                        "continuous — no sudden movement, no quick shift, no jump. The footage stays "
                        "sharp, crisp, and in focus with high detail throughout. " + camera_tail +
                        "Finish exactly in the same neutral pose as the reference for a smooth loop."
                    ),
                    seed=base_seed + attempt * 77,
                    video_profile=preparation_profile,
                    steps=8, num_frames=return_frames,
                )
                candidate = folder / "character-idle-return-candidate.mp4"
                await gateway.download(return_result["result"]["video_url"], candidate)
                jump = await asyncio.to_thread(self._max_translation_jump, candidate)
                if best_jump is None or jump < best_jump:
                    best_jump = jump
                    candidate.replace(return_raw)
                else:
                    candidate.unlink(missing_ok=True)
                if best_jump <= jump_limit:
                    break
            combined = folder / "character-idle-combined.mp4"
            await self._concat_clips(idle_raw, return_raw, combined,
                                     first_end_frame=outbound_end)
            return_raw.unlink(missing_ok=True)
            bridge.unlink(missing_ok=True)
            idle_raw.unlink(missing_ok=True)
            idle_raw = combined
        # LTX leaves a slow zoom/translation drift on the clip even with a
        # locked-off-camera prompt. Align every frame to the first frame
        # (background-referenced affine) so the camera is truly fixed.
        # 機械的なワープなので万能ではない(白背景での推定不安定などの実例あり)
        # — UIのカメラロック設定で無効化できる。FLF/復路の錨止めだけでも
        # ドリフトは「必ず元に戻る」範囲に収まる。
        idle_locked = folder / "character-idle-locked.mp4"
        if session.camera_lock_enabled:
            await asyncio.to_thread(self._lock_camera, idle_raw, idle_locked)
        else:
            shutil.copyfile(idle_raw, idle_locked)
        if neutral_target is not None:
            # Take the closed-mouth reference from the input-anchored clip start.
            await self._frame_at(idle_locked, neutral_target, 0.05)
        idle_video = target
        idle_slowdown = IDLE_MOTION_PROFILES.get(
            session.idle_motion_profile, IDLE_MOTION_PROFILES["wide"]
        )
        # The sequence starts and ends at the input pose (calm: FLF both ends,
        # lively: 往路+復路), so the full clip loops natively; shave one frame
        # so the anchor pose is not shown twice at the loop point.
        if lively:
            # 使用フレーム: 往路 0..outbound_end + 復路(先頭の重複を除く)。
            loop_seconds = (outbound_end + return_frames - 2) / idle_fps
        else:
            loop_seconds = idle_seconds - 1.0 / idle_fps
        await self._make_seamless_loop(
            idle_locked, idle_video,
            duration_seconds=loop_seconds,
            slowdown=idle_slowdown,
        )
        idle_raw.unlink(missing_ok=True)
        idle_locked.unlink(missing_ok=True)
        return idle_video

    # 既定の待機プール本数(セッション側 idle_pool_size で3〜5に変更可能。
    # 本数が多いほど巡回が長くなり、追い生成の頻度=会話との衝突確率が下がる)。
    IDLE_POOL_SIZE = 3

    async def _add_idle_to_pool(self, session: NarrationSession, gateway: GatewayClient,
                                folder: Path, character: Path,
                                neutral_target: Path | None = None) -> None:
        """Generate one idle clip and rotate it into the playback pool.

        Every clip starts and ends at the input pose, so the frontend can
        chain pool entries with a same-pose switch. Old entries beyond
        IDLE_POOL_SIZE are deleted from disk.
        """
        index = session.idle_pool_next
        session.idle_pool_next += 1
        target = folder / f"character-idle-{index:03}.mp4"
        await self._build_idle_loop(
            session, gateway, folder, character, target=target,
            base_seed=session.video_seed + index * 1009,
            neutral_target=neutral_target,
        )
        session.idle_videos.append(f"/api/sessions/{session.id}/idle-video/{index}")
        while len(session.idle_videos) > max(session.idle_pool_size, 3):
            dropped = session.idle_videos.pop(0)
            old_index = int(dropped.rsplit("/", 1)[1])
            (folder / f"character-idle-{old_index:03}.mp4").unlink(missing_ok=True)
        # Legacy single-video field keeps pointing at the newest entry.
        session.idle_video_url = session.idle_videos[-1]
        session.idle_video_ready_at = time()
        self.save(session)

    def _character_image(self, session: NarrationSession) -> Path:
        folder = self.settings.data_dir / session.id
        candidates = [p for p in folder.glob("character.*")
                      if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        if not candidates:
            raise RuntimeError("キャラクター画像が見つかりません")
        return candidates[0]

    # -- MiniMax-H3 engine (docs/h3-engine-plan.md) ------------------------------

    def _write_h3_anchor(self, session: NarrationSession, character: Path, target: Path) -> Path:
        """Speaking anchor: the character image cropped to the canvas aspect (native res)."""
        width, height = h3_profile_size(session.video_profile)
        return crop_to_aspect(character, target, width, height)

    def _h3_anchor(self, session: NarrationSession, character: Path, folder: Path) -> Path:
        """The one reference image reused by every chunk (cache-hit condition)."""
        anchor = folder / "character-neutral.png"
        if not anchor.is_file():
            self._write_h3_anchor(session, character, anchor)
        return anchor

    async def _build_idle_loop_h3(self, session: NarrationSession, gateway: GatewayClient,
                                  folder: Path, character: Path, target: Path,
                                  base_seed: int) -> Path:
        """H3 idle clip: fl2va with first = last = the canvas-fitted anchor, muted.

        Both frames must be cover-cropped to the exact canvas first: fl2va stretches
        `image` but cover-crops `last_image`, so any size mismatch stops the loop
        from closing (probe 2026-10-06: ends return to the anchor at 33 dB).
        """
        assert isinstance(gateway, H3GatewayClient)
        width, height = h3_profile_size(session.video_profile)
        closed_anchor = folder / H3_IDLE_ANCHOR_NAME
        if self.settings.h3_closed_idle_anchor and closed_anchor.is_file():
            # 閉口アンカー(キャンバス寸法そのもの、生成時に assert 済み)。opt-in:
            # 生成フレーム由来のため画質がやや荒く、既定は元画像の切り出しを使う
            # (ユーザー判定 2026-10-07)。唇が開いた画像のキャラ向けの選択肢。
            fitted = closed_anchor
        else:
            fitted = cover_crop(character, folder / "character-h3-canvas.png", width, height)
        image_id = await gateway.upload(fitted)
        result = await gateway.generate_blocking(
            gateway.idle_body(image_id=image_id, width=width, height=height, seed=base_seed))
        idle_raw = folder / "character-idle-raw.mp4"
        await gateway.download(result["result"]["video_url"], idle_raw)
        idle_locked = folder / "character-idle-locked.mp4"
        if session.camera_lock_enabled:
            await asyncio.to_thread(self._lock_camera, idle_raw, idle_locked)
        else:
            shutil.copyfile(idle_raw, idle_locked)
        # First and last frame are the anchor: shave one frame so the pose is not shown
        # twice at the loop point (same rule as the LTX FLF-anchored loop).
        clip_seconds = float(result["result"].get("duration_s") or H3_IDLE_SECONDS)
        await self._make_seamless_loop(
            idle_locked, target, duration_seconds=clip_seconds - 1.0 / 24.0, slowdown=1.0)
        idle_raw.unlink(missing_ok=True)
        idle_locked.unlink(missing_ok=True)
        return target

    async def _make_h3_closed_anchor(self, session: NarrationSession,
                                     gateway: GatewayClient, folder: Path,
                                     neutral: Path) -> Path:
        """Closed-mouth idle anchor: a silent 3 s ref2va, frame at t=1.0 s (2026-10-07 実測).

        The idle clips are fl2va with first = last = anchor, so an anchor with open lips
        gives an idle with an open mouth. vocal_lock freezes a silent wav -> the speaker
        keeps the lips closed. The reference is the same character-neutral.png every
        speaking chunk uses, so this job also warms the ref2va stack (compile + prefix /
        latent caches) — it replaces the separate 73f `_warm_h3` for a fresh session.
        """
        assert isinstance(gateway, H3GatewayClient)
        started = time()
        width, height = h3_profile_size(session.video_profile)
        silence = folder / "character-h3-closed-anchor.wav"
        raw = folder / "character-h3-closed-anchor.mp4"
        target = folder / H3_IDLE_ANCHOR_NAME
        try:
            seconds = h3_clip_seconds(3.0, gateway.min_seconds)
            silence.write_bytes(silent_wav(seconds))
            anchor_id, audio_id = await asyncio.gather(
                gateway.upload(neutral), gateway.upload(silence))
            body = gateway.closed_anchor_body(
                anchor_id=anchor_id, audio_id=audio_id, width=width, height=height,
                seed=session.video_seed)
            result = await gateway.generate_blocking(body)
            await gateway.download(result["result"]["video_url"], raw)
            await self._frame_at(raw, target, H3_CLOSED_ANCHOR_FRAME_S)
            got = image_size(target)
            if got != (width, height):
                target.unlink(missing_ok=True)
                raise RuntimeError(
                    f"閉口アンカーのサイズ {got} がプロファイル {(width, height)} と一致しません")
        finally:
            silence.unlink(missing_ok=True)
            raw.unlink(missing_ok=True)
        session.engine_prewarm_seconds = round(time() - started, 3)
        return target

    def start_h3_warmup(self, session: NarrationSession) -> None:
        """Warm the ref2va stack in the background (プラン §5b step 3). No-op for LTX."""
        if not self._is_h3(session):
            return
        existing = self.h3_warmups.get(session.id)
        if existing is not None and not existing.done():
            return
        self.h3_warmups[session.id] = asyncio.create_task(self._warm_h3(session))

    async def _warm_h3(self, session: NarrationSession) -> None:
        """One throw-away 73f ref2va clip so compile + prefix/latent caches are hot.

        Best effort: a failure here only means the first real chunk pays the warm-up.
        """
        started = time()
        try:
            gateway = self._gateway(session)
            assert isinstance(gateway, H3GatewayClient)
            await gateway.load_backend()
            folder = self.settings.data_dir / session.id
            anchor = self._h3_anchor(session, self._character_image(session), folder)
            width, height = h3_profile_size(session.video_profile)
            seconds = h3_clip_seconds(0.0, gateway.min_seconds)
            silence = folder / "character-h3-warmup.wav"
            silence.write_bytes(silent_wav(seconds))
            anchor_id, audio_id = await asyncio.gather(
                gateway.upload(anchor), gateway.upload(silence))
            await gateway.generate_blocking(gateway.chunk_body(
                anchor_id=anchor_id, audio_id=audio_id,
                prompt=self._prompt_h3("", session.concept, "low", "", ""),
                width=width, height=height, seconds=seconds, seed=session.video_seed))
            session.engine_prewarm_seconds = round(time() - started, 3)
            self.save(session)
        except Exception as exc:  # noqa: BLE001 - warm-up must never break a session
            logger.warning("H3 prewarm failed for %s: %s", session.id, exc)

    async def _ensure_h3_ready(self, session: NarrationSession, gateway: H3GatewayClient) -> None:
        """Start the H3 process unless a warm-up is already doing so (a no-op when running)."""
        warmup = self.h3_warmups.get(session.id)
        if warmup is not None and not warmup.done():
            return  # submit() retries 409 until the warm-up job and process are ready
        await gateway.load_backend()

    @staticmethod
    def _prompt_h3(text: str, concept: str, action_level: str = "low",
                   video_instruction: str = "", turn_video_instruction: str = "") -> str:
        """ref2va prompt. The speech is frozen from the wav (vocal_lock), so the prompt only
        directs framing, motion and who is speaking; the line is quoted as a hint."""
        setting = concept.strip() or "a calm, clean studio background"
        spoken_text = " ".join(text.split())[:300]
        action_direction = ACTION_DIRECTIONS.get(action_level, ACTION_DIRECTIONS["low"])
        standing = " ".join(video_instruction.split())[:1000]
        turn = " ".join(turn_video_instruction.split())[:1000]
        parts = [
            "The person in the reference image speaks naturally to the camera, front-facing "
            "or three-quarter view. The lips, teeth, and jaw move in sync with the supplied "
            "speech audio and rest closed in silence. Preserve the exact identity and "
            f"appearance of the reference. {action_direction} Stable camera. "
            f"Scene direction: {setting}."
        ]
        if standing:
            parts.append(f"Standing direction: {standing}.")
        if turn:
            parts.append(f"For this turn, follow precisely: {turn}.")
        if spoken_text:
            parts.append(f"She says: <d>{spoken_text}</d>")
        return " ".join(parts)

    async def regenerate_idle(self, session: NarrationSession) -> None:
        """Reset the idle pool and start over with the current settings.

        Generates one fresh clip for instant feedback; the frontend refill
        trigger grows the pool back to IDLE_POOL_SIZE during playback. The
        speaking anchors and the neutral reference stay untouched.
        """
        folder = self.settings.data_dir / session.id
        character = self._character_image(session)
        for url in session.idle_videos:
            old_index = int(url.rsplit("/", 1)[1])
            (folder / f"character-idle-{old_index:03}.mp4").unlink(missing_ok=True)
        session.idle_videos = []
        gateway = self._gateway(session)
        await gateway.load_backend()
        self.idle_clients[session.id] = gateway
        try:
            await self._add_idle_to_pool(session, gateway, folder, character)
        finally:
            self.idle_clients.pop(session.id, None)

    async def extend_idle_pool(self, session: NarrationSession) -> None:
        """Add one fresh clip to the pool (frontend refill trigger)."""
        folder = self.settings.data_dir / session.id
        character = self._character_image(session)
        gateway = self._gateway(session)
        await gateway.load_backend()
        self.idle_clients[session.id] = gateway
        try:
            await self._add_idle_to_pool(session, gateway, folder, character)
        finally:
            self.idle_clients.pop(session.id, None)

    async def prepare_character(self, session: NarrationSession, character: Path) -> None:
        """Preload LTX and create idle video plus the photoreal speaking reference."""
        started_at = time()
        session.status = SessionStatus.PREPARING
        session.error = None
        self.save(session)
        gateway = self._gateway(session)
        try:
            load_task = asyncio.create_task(gateway.load_backend())
            speech_task = None
            if session.character_mode == "photoreal" and not self._is_h3(session):
                anchor_text = "Ah. Ah. Ah. Ah." if session.conversation_language == "en" else "あー、あー、あー、あー。"
                speech_task = asyncio.create_task(synthesize_sentence(
                    self.settings.tts_url, session.voice_id, anchor_text
                ))
            await load_task
            folder = self.settings.data_dir / session.id
            # The closed-mouth reference for natural speech and all
            # articulation anchors comes from the camera-locked clip start.
            # 初期プールは常に3本だけ生成する(登録を速くするため。ユーザー発案)。
            # idle_pool_size が 4〜7 でも前払いはしない — _add_idle_to_pool は
            # 「追加→設定数を超えた分だけ最古を削除」なので、フロントの追い生成
            # (プール1周につき1本)がそのまま積み増しとして働き、満杯になるまで
            # 削除は発火しない。満杯後は従来どおり1本入替の回転になる。
            neutral = folder / "character-neutral.png"
            if self._is_h3(session):
                # H3: 発話アンカー(ref2va の参照)は入力画像をキャンバス比へ切り出した
                # 1枚を全チャンクで使い回す(同一画像の再利用が latent/prefix キャッシュの
                # ヒット条件)。LTX のような開口アンカー生成は不要。
                self._write_h3_anchor(session, character, neutral)
                # 閉口アンカー(無音 ref2va の t=1.0s)を前景で生成してから待機プールを作る。
                # この 1 本が ref2va スタックのプリワームを兼ねる(start_h3_warmup 不要)。
                await self._make_h3_closed_anchor(session, gateway, folder, neutral)
                self.save(session)
            for pool_index in range(3):
                await self._add_idle_to_pool(
                    session, gateway, folder, character,
                    neutral_target=neutral if pool_index == 0 and not self._is_h3(session) else None,
                )

            if speech_task is not None:
                # LTX 専用(h3 は speech_task を作らない)。VIDEO_PROFILES は LTX の表
                # なので、この参照を h3 経路に置くと KeyError になる(2026-10-06 実機)。
                preparation_profile = session.video_profile
                _, _, _, preparation_frames = VIDEO_PROFILES[preparation_profile]
                wav, _ = await speech_task
                condition = folder / "character-preparation.wav"
                condition.write_bytes(pad_wav(wav, 5.1))
                image_id, audio_id = await asyncio.gather(
                    gateway.upload(neutral), gateway.upload(condition)
                )
                # The speaking anchor is reused by every clip, including full-size
                # follow-ups. Generate it at the selected resolution; only the first
                # conversational clip uses the lower-latency startup profile.
                result = await gateway.generate(
                    image_id, audio_id,
                    "Medium close-up of the same character repeatedly articulating sustained open vowel "
                    "sounds. The mouth opens wide and visibly for every vowel; lips, teeth, and jaw are "
                    "clearly visible. Stable identity and camera.",
                    session.video_seed, preparation_profile, 8, preparation_frames, 1.3,
                )
                raw = folder / "character-preparation.mp4"
                await gateway.download(result["result"]["video_url"], raw)
                # Repeated vowels create a stable open-mouth interval at full
                # resolution. Extract four progressively later articulation frames
                # so the UI can finely tune mouth motion without another LTX job.
                await self._frame_at(raw, folder / "character-speaking-balanced.png", 0.12)
                await self._frame_at(raw, folder / "character-speaking-medium.png", 0.33)
                await self._frame_at(raw, folder / "character-speaking-medium-strong.png", 0.54)
                await self._frame_at(raw, folder / "character-speaking.png", 0.75)
                raw.unlink(missing_ok=True)
            session.character_prepared = True
            session.character_preparation_seconds = round(time() - started_at, 3)
            session.status = SessionStatus.QUEUED
            self.save(session)
            # H3 のプリワームは上の閉口アンカー生成(無音 ref2va)が兼ねるため、ここでは
            # start_h3_warmup しない。プリセット復元(main.restore_preset)は閉口アンカーが
            # ディスクにあり再生成しないので、そちらだけ従来の軽い 73f ウォームを維持する。
        except Exception as exc:
            session.status = SessionStatus.FAILED
            session.error = str(exc)
            self.save(session)
            raise

    async def _run_chat(self, session: NarrationSession, character: Path,
                        narration_text: str | None = None,
                        turn_video_instruction: str = "",
                        turn_anchor: Path | None = None) -> None:
        folder = self.settings.data_dir / session.id
        gateway = self._gateway(session)
        is_h3 = self._is_h3(session)
        # 会話ターンの間、リアルタイム優先リースを保持する(H3 などの長尺ジョブを
        # gateway が入口で 409 にする)。ターンの頭で取得しないと、直前に滑り込んだ
        # H3 t2va(約25秒・中断不可)で最初のチャンクが丸ごと遅れる。renew は
        # チャンク進行と無関係に 20 秒周期(TTL 60秒の 1/3)で回す — チャンク間隔は
        # 負荷で伸びるので同期させない。**待機プール補充ではリースを取らない**こと
        # (取ると H3 が永久に回らなくなる)。全て最善努力で、リース API の無い
        # gateway でも会話は従来どおり動く。
        lease_id = await gateway.acquire_lease()

        async def renew_lease() -> None:
            nonlocal lease_id
            while True:
                await asyncio.sleep(20.0)
                # 他ターンとリースを共有していて先に release された場合、renew は
                # 新しいリースとして受理される(id が変わる)ので必ず取り直す
                lease_id = await gateway.acquire_lease(lease_id)

        lease_renewer = asyncio.create_task(renew_lease())
        llm = None if narration_text is not None else StreamingChatClient(
            self.settings.llm_url, self.settings.llm_model, self.settings.llm_api_key
        )
        tts_queue: asyncio.Queue[tuple[asyncio.Task, str, float] | None] = asyncio.Queue()
        video_queue: asyncio.Queue[Chunk | None] = asyncio.Queue()
        assistant_parts: list[str] = []
        session.assistant_text = ""
        # H3 のクリップ長は 17n+5 フレーム格子(3.04/4.46/5.875/7.29s…)にサーバが丸める。
        # 丸め後長 ≥ 発話長だけ保証すればよいので、LTX の固定尺の代わりに最小格子を使う。
        h3_min_seconds = getattr(gateway, "min_seconds", 3.0)
        clip_duration = (h3_clip_seconds(0.0, h3_min_seconds) if is_h3
                         else profile_duration(session.video_profile))

        async def assemble_audio() -> None:
            elapsed = sum(float(item.duration or 0) for item in session.chunks)
            parts: list[SpeechPart] = []
            parts_duration = 0.0
            started_at: float | None = None
            first_of_turn = True

            # H3: 先頭チャンクは 3.04s(73f)に収まる短さで早く出し、後続は 5.875s 格子に
            # 収まる長さ(session.target_chunk_seconds=5.8)まで貯める。LTX は従来どおり。
            first_target = self.settings.h3_first_chunk_seconds

            async def emit() -> None:
                nonlocal elapsed, parts, parts_duration, started_at, first_of_turn
                if not parts:
                    return
                index = len(session.chunks)
                # Long speech is allowed to outlast the fixed LTX video. The
                # browser holds the final video frame until the original audio ends.
                chunk_duration = max(clip_duration, parts_duration)
                audio = folder / f"chunk-{index:03}.wav"
                original_wav = join_wavs([part.wav for part in parts])
                audio.write_bytes(original_wav)
                if is_h3:
                    # 条件音声をサーバが生成するクリップ長ちょうどへ無音パディングする
                    # (vocal_lock は音声 latent 全長を固定するので、発話後は無音に固定される)。
                    chunk_duration = max(h3_clip_seconds(parts_duration, h3_min_seconds),
                                         parts_duration)
                    (folder / f"chunk-{index:03}-condition.wav").write_bytes(
                        pad_wav(original_wav, chunk_duration)
                    )
                else:
                    (folder / f"chunk-{index:03}-condition.wav").write_bytes(
                        pad_wav(original_wav, chunk_duration + 0.1)
                    )
                chunk = Chunk(
                    index=index, text="".join(part.text for part in parts), status="audio_ready",
                    duration=round(chunk_duration, 3), speech_duration=round(parts_duration, 3),
                    timeline_start=round(elapsed, 3),
                    audio_url=f"/api/sessions/{session.id}/chunks/{index}/audio",
                    tts_started_at=started_at, audio_ready_at=time(),
                )
                session.chunks.append(chunk)
                elapsed += chunk_duration
                parts, parts_duration, started_at = [], 0.0, None
                first_of_turn = False
                self.save(session)
                await video_queue.put(chunk)

            while True:
                queued = await tts_queue.get()
                if queued is None:
                    break
                task, text, part_started_at = queued
                wav, part_duration = await task
                part = SpeechPart(text, wav, part_duration)
                # Do not merge another sentence when it would push the spoken
                # chunk past the configured target. The previous 65% threshold
                # favored fewer clips but frequently produced six-second chunks.
                if (is_h3 and first_of_turn and parts
                        and parts_duration + part_duration > first_target):
                    await emit()
                if parts and parts_duration + part_duration > session.target_chunk_seconds:
                    await emit()
                if not parts:
                    started_at = part_started_at
                parts.append(part)
                parts_duration += part_duration
                # Start immediately on a complete sentence, but do not turn an
                # introductory comma clause into its own five-second video.
                complete_sentence = text.rstrip().endswith(("。", "！", "？", "!", "?"))
                if ((first_of_turn and complete_sentence)
                        or (is_h3 and first_of_turn and parts_duration >= first_target)
                        or parts_duration >= session.target_chunk_seconds):
                    await emit()
            await emit()
            # ここでターンの最終チャンクが確定する。動画生成はTTSより遅いので、
            # このフラグは通常まだ生成前のチャンクに立つ(間に合わなければ従来
            # どおり末尾アンカーなしで生成されるだけ — 劣化は起きない)。
            if session.chunks:
                session.chunks[-1].turn_final = True
            await video_queue.put(None)

        async def generate_video() -> None:
            first_video_of_turn = True
            chain_path = character
            uploaded_images: dict[Path, str] = {}

            async def image_asset(path: Path) -> str:
                if path not in uploaded_images:
                    uploaded_images[path] = await gateway.upload(path)
                return uploaded_images[path]

            def photoreal_reference() -> Path:
                candidates = {
                    "natural": folder / "character-neutral.png",
                    "balanced": folder / "character-speaking-balanced.png",
                    "medium": folder / "character-speaking-medium.png",
                    "medium_strong": folder / "character-speaking-medium-strong.png",
                    "strong": folder / "character-speaking.png",
                    # Backward compatibility for sessions created before the
                    # natural/balanced/strong modes were introduced.
                    "fast": folder / "character-speaking.png",
                }
                selected = candidates.get(session.lip_sync_mode, candidates["natural"])
                if selected.is_file():
                    return selected
                # Sessions prepared before the intermediate modes were added do
                # not have their two extra anchor images yet.
                legacy_fallbacks = {
                    "medium": candidates["balanced"],
                    "medium_strong": candidates["strong"],
                }
                fallback = legacy_fallbacks.get(session.lip_sync_mode)
                return fallback if fallback is not None and fallback.is_file() else character

            while True:
                chunk = await video_queue.get()
                if chunk is None:
                    break
                if session.cancelled:
                    return
                chunk.status = "video_generating"
                chunk.video_started_at = time()
                session.status = SessionStatus.GENERATING
                self.save(session)
                if (first_video_of_turn and turn_anchor is not None
                        and session.turn_anchor_mode == "idle_frame"
                        and turn_anchor.is_file()):
                    # 連続性優先: 送信時に表示していた待機フレームから話し始める。
                    # 実写で口が開きにくくなったら「会話の開始画像」を従来の
                    # 発話アンカーに戻すこと(閉口参照×実写プライアの既知問題)。
                    reference = turn_anchor
                else:
                    reference = photoreal_reference() if session.character_mode == "photoreal" else chain_path
                image_id = await image_asset(reference)
                audio_path = folder / f"chunk-{chunk.index:03}.wav"
                condition_audio = folder / f"chunk-{chunk.index:03}-condition.wav"
                audio_id = await gateway.upload(condition_audio)
                actual_profile = generation_profile(session.video_profile, first_video_of_turn)
                actual_steps = (
                    min(4, session.video_steps) if first_video_of_turn else session.video_steps
                )
                # Keep photoreal motion reproducible with the selected seed. Standard
                # mode offsets each chunk so chained clips do not repeat the same motion.
                actual_seed = session.video_seed if session.character_mode == "photoreal" else session.video_seed + chunk.index
                actual_modality_scale = (
                    1.3
                    if session.modality_scale_enabled
                    and session.character_mode == "photoreal"
                    and session.lip_sync_mode in {
                        "natural", "balanced", "medium", "medium_strong", "strong"
                    }
                    else None
                )
                _, _, _, profile_frames = VIDEO_PROFILES[actual_profile]
                actual_frames = profile_frames
                chunk.generated_profile = actual_profile
                chunk.generated_steps = actual_steps
                chunk.generated_seed = actual_seed
                chunk.generated_frames = actual_frames
                chunk.audio_modality_scale = None
                chunk.modality_scale = actual_modality_scale
                # ターン終い(ユーザー案): 最終チャンクの末尾をキャラクター入力
                # 画像(=待機クリップの開始ポーズ)へFLF錨止めし、会話→待機の
                # 切替を同ポーズにする。末尾錨止めは動きを抑える副作用がある
                # ため設定で切替(既定=従来)。
                end_anchor_id = None
                if (chunk.turn_final and session.turn_end_mode == "return_idle"):
                    end_anchor_id = await image_asset(character)
                result = await gateway.generate(
                    image_id, audio_id, self._prompt(
                        chunk.text, session.concept, session.character_mode, session.action_level,
                        session.video_instruction, turn_video_instruction,
                    ),
                    actual_seed, actual_profile, actual_steps, actual_frames,
                    actual_modality_scale,
                    last_image_id=end_anchor_id,
                )
                first_video_of_turn = False
                raw = folder / f"chunk-{chunk.index:03}-raw.mp4"
                await gateway.download(result["result"]["video_url"], raw)
                output = folder / f"chunk-{chunk.index:03}.mp4"
                # Keep the full original TTS waveform. If it outlasts the fixed LTX
                # video, the media element retains the last frame until speech ends.
                await mux_original_audio(raw, audio_path, output)
                raw.unlink(missing_ok=True)
                if session.character_mode == "standard":
                    chain_path = folder / f"chain-{chunk.index:03}.png"
                    await self._last_frame(output, chain_path)
                chunk.video_url = f"/api/sessions/{session.id}/chunks/{chunk.index}/video"
                chunk.generation_seconds = result["result"].get("generation_seconds")
                chunk.status = "playable"
                chunk.video_ready_at = time()
                if sum(item.status == "playable" for item in session.chunks) >= session.startup_buffer_chunks:
                    session.status = SessionStatus.PLAYABLE
                self.save(session)

        async def generate_video_h3() -> None:
            """H3 ref2va chunk pipeline.

            Unlike the LTX loop (one job at a time, end to end), consecutive chunks
            overlap: chunk N+1 is submitted as soon as chunk N is confirmed running
            at the backend, and the gateway admits it the moment N's denoise frees the
            backend lock (N then decodes on the second GPU). Waiting, downloading and
            publishing of each chunk run in its own finisher task.
            """
            assert isinstance(gateway, H3GatewayClient)
            width, height = h3_profile_size(session.video_profile)
            # 初回チャンクは1ランク下の解像度で初動を削る(LTX の startup 相当)。
            # アスペクト比はほぼ同一なので参照アンカーは共用する。
            startup_w, startup_h = (
                h3_startup_size(session.video_profile)
                if self.settings.h3_startup_lowres else (width, height)
            )
            await self._ensure_h3_ready(session, gateway)
            anchor = self._h3_anchor(session, character, folder)
            anchor_id = await gateway.upload(anchor)
            turn_anchor_id: str | None = None
            if (turn_anchor is not None and session.turn_anchor_mode == "idle_frame"
                    and turn_anchor.is_file()):
                turn_ref = crop_to_aspect(turn_anchor, folder / "turn-anchor-h3.png", width, height)
                turn_anchor_id = await gateway.upload(turn_ref)
            first_video_of_turn = True
            finishers: list[asyncio.Task] = []
            previous_done: float | None = None

            async def finish(chunk: Chunk, job_id: str, started_at: float,
                             needs_mux: bool, body: dict | None = None) -> None:
                nonlocal previous_done
                try:
                    try:
                        result = await gateway.wait(job_id)
                    except GatewayError as exc:
                        # 受理(202)後にバックエンド 409 で failed になるレース(別セッションの
                        # 待機補充との衝突)。1 回だけ再投入する(gateway.py の is_busy_failure 参照)。
                        if body is None or not gateway.is_busy_failure(exc):
                            raise
                        job_id = await gateway.submit(body)
                        result = await gateway.wait(job_id)
                    done_at = time()
                    raw = folder / f"chunk-{chunk.index:03}-raw.mp4"
                    await gateway.download(result["result"]["video_url"], raw)
                    output = folder / f"chunk-{chunk.index:03}.mp4"
                    if needs_mux:
                        # Speech longer than the longest H3 clip: restore the full TTS audio
                        # (the browser holds the last frame until it ends, as with LTX).
                        await mux_original_audio(raw, folder / f"chunk-{chunk.index:03}.wav", output)
                        raw.unlink(missing_ok=True)
                    else:
                        # H3 already muxed the conditioning audio (waveform corr. 0.997).
                        raw.replace(output)
                except Exception as exc:
                    chunk.status, chunk.error = "failed", str(exc)
                    self.save(session)
                    raise
                chunk.video_url = f"/api/sessions/{session.id}/chunks/{chunk.index}/video"
                chunk.generation_seconds = round(done_at - started_at, 3)
                chunk.status = "playable"
                chunk.video_ready_at = time()
                if previous_done is not None:
                    sample = done_at - previous_done
                    old = session.engine_cadence_seconds
                    session.engine_cadence_seconds = round(
                        sample if old is None else 0.5 * old + 0.5 * sample, 3)
                previous_done = done_at
                if sum(item.status == "playable" for item in session.chunks) >= session.startup_buffer_chunks:
                    session.status = SessionStatus.PLAYABLE
                self.save(session)

            async def next_chunk() -> Chunk | None:
                getter = asyncio.ensure_future(video_queue.get())
                try:
                    while True:
                        pending = {item for item in finishers if not item.done()}
                        await asyncio.wait({getter, *pending}, return_when=asyncio.FIRST_COMPLETED)
                        for item in finishers:
                            if item.done() and not item.cancelled() and item.exception() is not None:
                                raise item.exception()
                        if getter.done():
                            return getter.result()
                finally:
                    if not getter.done():
                        getter.cancel()

            try:
                while True:
                    chunk = await next_chunk()
                    if chunk is None or session.cancelled:
                        break
                    chunk.status = "video_generating"
                    chunk.video_started_at = time()
                    session.status = SessionStatus.GENERATING
                    self.save(session)
                    steps = min(H3_STEPS, session.video_steps) if first_video_of_turn else session.video_steps
                    seed = (session.video_seed if session.character_mode == "photoreal"
                            else session.video_seed + chunk.index)
                    reference_id = anchor_id
                    if first_video_of_turn and turn_anchor_id is not None:
                        reference_id = turn_anchor_id
                    audio_id = await gateway.upload(folder / f"chunk-{chunk.index:03}-condition.wav")
                    clip_seconds = h3_clip_seconds(min(chunk.duration or 0.0, 15.0), h3_min_seconds)
                    chunk.generated_profile = session.video_profile
                    chunk.generated_steps = steps
                    chunk.generated_seed = seed
                    chunk.generated_frames = round(clip_seconds * 24)
                    chunk_w, chunk_h = (startup_w, startup_h) if first_video_of_turn else (width, height)
                    body = gateway.chunk_body(
                        anchor_id=reference_id, audio_id=audio_id,
                        prompt=self._prompt_h3(
                            chunk.text, session.concept, session.action_level,
                            session.video_instruction, turn_video_instruction),
                        width=chunk_w, height=chunk_h, seconds=clip_seconds, seed=seed, steps=steps)
                    # Returns once the backend really started this job (投入規律, プラン §4-1).
                    job_id = await gateway.submit(body)
                    first_video_of_turn = False
                    needs_mux = (chunk.speech_duration or 0.0) > clip_seconds + 0.05
                    finishers.append(asyncio.create_task(
                        finish(chunk, job_id, time(), needs_mux, body)))
                await asyncio.gather(*finishers)
            finally:
                for item in finishers:
                    if not item.done():
                        item.cancel()

        try:
            session.status = (
                SessionStatus.SYNTHESIZING if narration_text is not None else SessionStatus.CHATTING
            )
            session.error = None
            session.llm_started_at = None if narration_text is not None else time()
            session.llm_first_delta_at = None
            session.llm_completed_at = None
            self.save(session)

            async def receiver_with_labels() -> None:
                if narration_text is not None:
                    fragments, _ = pop_speakable(
                        narration_text, force=True, language=session.conversation_language
                    )
                    for fragment in fragments:
                        task = asyncio.create_task(synthesize_sentence(
                            self.settings.tts_url, session.voice_id, fragment
                        ))
                        await tts_queue.put((task, fragment, time()))
                        # Bound direct-reading concurrency for very long pasted
                        # documents while video generation continues in parallel.
                        await task
                    await tts_queue.put(None)
                    return

                assert llm is not None
                history = [{"role": "system", "content": system_prompt(session.conversation_language)}]
                history.extend(item.model_dump() for item in session.messages[-20:])
                buffer = ""
                async for delta in llm.stream(history):
                    if session.llm_first_delta_at is None:
                        session.llm_first_delta_at = time()
                    assistant_parts.append(delta)
                    session.assistant_text = "".join(assistant_parts)
                    buffer += delta
                    fragments, buffer = pop_speakable(buffer, language=session.conversation_language)
                    for fragment in fragments:
                        task = asyncio.create_task(synthesize_sentence(
                            self.settings.tts_url, session.voice_id, fragment
                        ))
                        tts_queue.put_nowait((task, fragment, time()))
                    self.save(session)
                fragments, _ = pop_speakable(
                    buffer, force=True, language=session.conversation_language
                )
                for fragment in fragments:
                    task = asyncio.create_task(synthesize_sentence(
                        self.settings.tts_url, session.voice_id, fragment
                    ))
                    tts_queue.put_nowait((task, fragment, time()))
                session.llm_completed_at = time()
                await tts_queue.put(None)

            async with asyncio.TaskGroup() as group:
                group.create_task(receiver_with_labels())
                group.create_task(assemble_audio())
                group.create_task(generate_video_h3() if is_h3 else generate_video())
            answer = "".join(assistant_parts).strip()
            if answer:
                session.messages.append(ChatMessage(role="assistant", content=answer))
            session.status = SessionStatus.CANCELLED if session.cancelled else SessionStatus.COMPLETED
            self.save(session)
        except asyncio.CancelledError:
            session.status = SessionStatus.CANCELLED
            self.save(session)
            raise
        except Exception as exc:
            session.status = SessionStatus.FAILED
            # TaskGroup wraps the useful error; expose its leaf message where possible.
            leaf = exc.exceptions[0] if isinstance(exc, BaseExceptionGroup) and exc.exceptions else exc
            session.error = str(leaf)
            pending = next((item for item in session.chunks if item.status == "video_generating"), None)
            if pending:
                pending.status, pending.error = "failed", str(leaf)
            self.save(session)
        finally:
            # ターン終了 = 会話セッション宣言の解除。キャンセル・失敗経路でも必ず通す
            # (解放漏れは TTL 60 秒で自動失効するが、その間 H3 が無駄に待つ)。
            lease_renewer.cancel()
            await gateway.release_lease(lease_id)

    @staticmethod
    def _prompt(text: str, concept: str, character_mode: str = "photoreal",
                action_level: str = "low", video_instruction: str = "",
                turn_video_instruction: str = "") -> str:
        setting = concept.strip() or "a calm, clean studio background"
        spoken_text = " ".join(text.split())[:300]
        action_direction = ACTION_DIRECTIONS.get(action_level, ACTION_DIRECTIONS["low"])
        standing_instruction = " ".join(video_instruction.split())[:1000]
        turn_instruction = " ".join(turn_video_instruction.split())[:1000]
        directed_parts: list[str] = []
        if standing_instruction:
            directed_parts.append(
                "Follow this standing user video instruction while preserving identity, the visible face, lip "
                "synchronization, and stable continuity. It takes priority over the general motion and scene "
                f"guidance: {standing_instruction}."
            )
        if turn_instruction:
            directed_parts.append(
                "For this turn, follow this inline video instruction precisely. It takes priority over the "
                f"standing instruction and the general motion and scene guidance: {turn_instruction}."
            )
        directed_action = f" {' '.join(directed_parts)}" if directed_parts else ""
        mouth_rest = (
            "Mouth movement is only for articulating the narration; do not hold an open-mouth expression. "
            "During silent intervals, the lips rest naturally together. "
        )
        if character_mode == "standard":
            return (
                "Medium close-up of the same character speaking naturally, front-facing or three-quarter view. "
                "The full face and unobstructed mouth stay clearly visible. Natural lip and jaw movement follows "
                f"the supplied narration audio. {mouth_rest}{action_direction} "
                "Stable camera and consistent identity. "
                f'Scene direction: {setting}.{directed_action} The character says: "{spoken_text}".'
            )
        return (
            f'The character says exactly: "{spoken_text}". '
            "Clearly and continuously articulate every spoken syllable, with visible rhythmic mouth opening "
            "and closing synchronized to the supplied speech audio. The mouth must not remain closed while "
            "speaking. After the supplied speech ends, stop articulating and naturally return the lips to a "
            "relaxed closed position for the remaining silence. Smoothly return the head, body, and calm "
            f"expression to the input reference pose in the final frames. {mouth_rest}"
            "Medium close-up of the same character, "
            "front-facing or three-quarter view. The full "
            "face, lips, teeth, and jaw remain unobstructed and clearly visible. Preserve identity, with subtle "
            f"blinking and breathing, and a stable camera. {action_direction} Scene direction: {setting}."
            f"{directed_action}"
        )

    @staticmethod
    async def _last_frame(video: Path, target: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-sseof", "-0.5", "-i", str(video),
            "-frames:v", "1", str(target), stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode or not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"最終フレーム抽出に失敗しました: {stderr.decode()[-500:]}")

    @staticmethod
    async def _frame_at(video: Path, target: Path, seconds: float) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-i", str(video), "-ss", f"{seconds:.3f}",
            "-frames:v", "1", str(target), stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode or not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"発話用フレーム抽出に失敗しました: {stderr.decode()[-500:]}")

    @staticmethod
    def _lock_camera(video: Path, target: Path) -> None:
        """Warp every frame onto the first frame to cancel camera drift.

        Estimates a dense affine alignment of every frame against frame 0
        with ECC on downscaled, blurred luma, restricted to the frame border
        (the centre is masked out): the border is background, so the fit
        captures the camera component only and the subject's own sway,
        blinks, and breathing survive the correction (2026-09-14 実測:
        全面推定は被写体の動きまで2.19→1.2に削っていた。周縁マスクで1.7を保持
        しつつ背景の残留ズームは0.08%). Warm-starts each frame from the
        previous solution; the inverse warp pins the camera to frame 0. A
        small fixed crop-zoom hides the replicated warp borders. Runs in a
        worker thread; frames pass through unwarped when ECC fails.
        """
        import cv2
        import numpy as np

        capture = cv2.VideoCapture(str(video))
        frames = []
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
        fps = capture.get(cv2.CAP_PROP_FPS) or 16.0
        capture.release()
        if len(frames) < 2:
            shutil.copyfile(video, target)
            return
        height, width = frames[0].shape[:2]
        scale = 0.25

        def small_luma(frame):
            luma = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            luma = cv2.resize(luma, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            return cv2.GaussianBlur(luma, (5, 5), 0).astype(np.float32)

        reference = small_luma(frames[0])
        small_h, small_w = reference.shape
        border_mask = np.ones((small_h, small_w), np.uint8)
        border_mask[int(small_h * 0.15):int(small_h * 0.85),
                    int(small_w * 0.2):int(small_w * 0.8)] = 0
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)

        def sanitize(raw: np.ndarray) -> np.ndarray | None:
            """Project the affine fit to a similarity and reject wild fits.

            The full 6-DOF affine admits shear and anisotropic stretch, and a
            fit polluted by subject motion (hair/body entering the border
            mask) warps the image visibly (2026-09-14 実測: 非等方4.3%・回転
            2.8°・並進14px が混入して「画像が歪む」)。A camera on a tripod can
            only drift by a tiny uniform zoom/rotation/shift, so anything
            larger is a bad estimate, not the camera.
            """
            linear = raw[:2, :2].astype(np.float64)
            u, singular, vt = np.linalg.svd(linear)
            rotation = u @ vt
            if np.linalg.det(rotation) < 0:
                return None
            uniform = float(singular.mean())
            angle = np.arctan2(rotation[1, 0], rotation[0, 0])
            tx, ty = float(raw[0, 2]) / scale, float(raw[1, 2]) / scale
            if not (0.97 <= uniform <= 1.03 and abs(angle) <= np.radians(1.0)
                    and abs(tx) <= 0.02 * width and abs(ty) <= 0.02 * height):
                return None
            similarity = np.eye(3)
            similarity[:2, :2] = uniform * rotation
            similarity[0, 2], similarity[1, 2] = tx, ty
            return similarity
        margin = 0.02
        crop = np.array([
            [1 + 2 * margin, 0, -margin * width],
            [0, 1 + 2 * margin, -margin * height],
            [0, 0, 1],
        ], dtype=np.float64)
        warp = np.eye(2, 3, dtype=np.float32)
        encoder = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{width}x{height}", "-r", f"{fps}", "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-pix_fmt", "yuv420p", str(target)],
            stdin=subprocess.PIPE,
        )
        try:
            # Applied correction as (scale, angle, tx, ty). Real tripod drift
            # is slow, so the correction may only change a whisker per frame —
            # without this rate limit, textureless borders (白背景) let the ECC
            # fit hop between solutions and the "correction" itself injects
            # 10px級の位置飛びを起こす(2026-09-14 実測: raw 1.1px → lock後 11.5px).
            applied_params = np.array([1.0, 0.0, 0.0, 0.0])
            step_limits = np.array([0.0015, np.radians(0.05), 0.5, 0.5])
            good_warp = warp.copy()

            def to_matrix(params):
                s, angle, tx, ty = params
                matrix = np.eye(3)
                matrix[0, 0] = s * np.cos(angle)
                matrix[0, 1] = -s * np.sin(angle)
                matrix[1, 0] = s * np.sin(angle)
                matrix[1, 1] = s * np.cos(angle)
                matrix[0, 2], matrix[1, 2] = tx, ty
                return matrix

            for index, frame in enumerate(frames):
                if index:
                    try:
                        _, warp = cv2.findTransformECC(
                            reference, small_luma(frame), warp.copy(),
                            cv2.MOTION_AFFINE, criteria, border_mask, 5)
                    except cv2.error:
                        pass  # keep the previous warp — drift changes slowly
                    similarity = sanitize(warp)
                    if similarity is None:
                        # Bad fit: keep the last good correction and restart
                        # the warm start from it so the error cannot snowball.
                        warp = good_warp.copy()
                    else:
                        target = np.array([
                            float(np.hypot(similarity[0, 0], similarity[1, 0])),
                            float(np.arctan2(similarity[1, 0], similarity[0, 0])),
                            float(similarity[0, 2]), float(similarity[1, 2]),
                        ])
                        delta = np.clip(target - applied_params, -step_limits, step_limits)
                        applied_params = applied_params + delta
                        good_warp = warp.copy()
                applied = to_matrix(applied_params)
                correction = crop @ np.linalg.inv(applied)
                warped = cv2.warpAffine(frame, correction[:2], (width, height),
                                        flags=cv2.INTER_LANCZOS4,
                                        borderMode=cv2.BORDER_REPLICATE)
                encoder.stdin.write(warped.tobytes())
        finally:
            encoder.stdin.close()
            encoder.wait()
        if encoder.returncode:
            shutil.copyfile(video, target)

    @staticmethod
    def _max_translation_jump(video: Path) -> float:
        """Largest frame-to-frame subject translation (px, phase correlation).

        Sudden position snaps (9〜13px/フレーム、通常は~0.4px) は生成に焼き込まれて
        いてプロンプトでは防げない(2026-09-14 実測)。検出してseedを変えて引き直す。
        """
        import cv2
        import numpy as np

        capture = cv2.VideoCapture(str(video))
        previous = None
        worst = 0.0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame[h // 6:h * 5 // 6, w // 6:w * 5 // 6],
                                cv2.COLOR_BGR2GRAY).astype(np.float32)
            if previous is not None:
                (dx, dy), _ = cv2.phaseCorrelate(previous, gray)
                worst = max(worst, float((dx * dx + dy * dy) ** 0.5))
            previous = gray
        capture.release()
        return worst

    @staticmethod
    def _select_bridge(video: Path, bridge: Path) -> int:
        """Pick the sharpest low-motion frame near the clip end as the bridge.

        Conditioning the return clip on a motion-blurred frame degrades its
        whole output, so among the final 40% of frames only those with
        below-median inter-frame motion are considered, and the one with the
        highest Laplacian sharpness wins. Returns the chosen frame index.
        """
        import cv2
        import numpy as np

        capture = cv2.VideoCapture(str(video))
        frames = []
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
        capture.release()
        if len(frames) < 8:
            cv2.imwrite(str(bridge), frames[-1])
            return len(frames) - 1
        start = int(len(frames) * 0.6)
        candidates = []
        for i in range(start, len(frames)):
            gray = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            motion = float(np.mean(np.abs(frames[i].astype(np.int16)
                                          - frames[i - 1].astype(np.int16))))
            candidates.append((i, sharpness, motion))
        median_motion = float(np.median([m for _, _, m in candidates]))
        settled = [c for c in candidates if c[2] <= median_motion] or candidates
        best = max(settled, key=lambda c: c[1])[0]
        cv2.imwrite(str(bridge), frames[best])
        return best

    @staticmethod
    async def _concat_clips(first: Path, second: Path, target: Path,
                            first_end_frame: int | None = None) -> None:
        """Join the outbound clip and the return clip into one sequence.

        The outbound clip is cut right after the bridge frame and the return
        clip is conditioned on that frame, so the return clip's first frame
        duplicates it and gets dropped at the junction.
        """
        first_trim = "" if first_end_frame is None else f"trim=end_frame={first_end_frame + 1},"
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-i", str(first), "-i", str(second),
            "-filter_complex",
            f"[0:v]{first_trim}setpts=PTS-STARTPTS[out0];"
            "[1:v]trim=start_frame=1,setpts=PTS-STARTPTS[ret];"
            "[out0][ret]concat=n=2:v=1:a=0,format=yuv420p[out]",
            "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            str(target), stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode or not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"待機動画の連結に失敗しました: {stderr.decode()[-500:]}")

    @staticmethod
    async def _make_seamless_loop(video: Path, target: Path,
                                  duration_seconds: float | None = None,
                                  slowdown: float = 1.0) -> None:
        """Re-encode a natively loopable clip (FLF-anchored ends) for display.

        Trims the duplicated anchor pose off the tail and optionally slows
        playback. No ping-pong: the reverse pass used to mirror every blink
        and turn residual drift into a visible in/out oscillation.
        """
        duration = "" if duration_seconds is None else f":duration={max(0.05, duration_seconds):.3f}"
        speed = max(1.0, slowdown)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-i", str(video),
            "-filter_complex",
            f"[0:v]trim=start=0{duration},setpts={speed:.3f}*(PTS-STARTPTS),format=yuv420p[out]",
            "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(target), stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode or not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"待機ループ動画の加工に失敗しました: {stderr.decode()[-500:]}")
