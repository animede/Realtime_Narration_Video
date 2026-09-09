from __future__ import annotations

import asyncio
from pathlib import Path
from time import time

from .chunker import SpeechPart
from .config import Settings
from .gateway import VIDEO_PROFILES, GatewayClient, generation_profile, profile_duration
from .llm import StreamingChatClient, pop_speakable
from .models import ChatMessage, Chunk, NarrationSession, SessionStatus
from .muxer import mux_original_audio
from .tts import join_wavs, pad_wav, silent_wav, synthesize_sentence


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


def system_prompt(language: str) -> str:
    return {"ja": SYSTEM_PROMPT_JA, "en": SYSTEM_PROMPT_EN}.get(language, SYSTEM_PROMPT_AUTO)


class Orchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, NarrationSession] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        settings.data_dir.mkdir(parents=True, exist_ok=True)

    def register(self, session: NarrationSession) -> None:
        self.sessions[session.id] = session

    def chat(self, session: NarrationSession, character: Path) -> None:
        self.sessions[session.id] = session
        self.tasks[session.id] = asyncio.create_task(self._run_chat(session, character))

    def narrate(self, session: NarrationSession, character: Path, text: str) -> None:
        """Speak supplied text directly without sending it to the LLM."""
        self.sessions[session.id] = session
        self.tasks[session.id] = asyncio.create_task(
            self._run_chat(session, character, narration_text=text)
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

    async def prepare_character(self, session: NarrationSession, character: Path) -> None:
        """Preload LTX and create idle video plus the photoreal speaking reference."""
        started_at = time()
        session.status = SessionStatus.PREPARING
        session.error = None
        self.save(session)
        gateway = GatewayClient(self.settings.gateway_url, self.settings.gateway_preset,
                                self.settings.poll_interval)
        try:
            load_task = asyncio.create_task(gateway.load_backend())
            speech_task = None
            if session.character_mode == "photoreal":
                anchor_text = "Ah. Ah. Ah. Ah." if session.conversation_language == "en" else "あー、あー、あー、あー。"
                speech_task = asyncio.create_task(synthesize_sentence(
                    self.settings.tts_url, session.voice_id, anchor_text
                ))
            await load_task
            folder = self.settings.data_dir / session.id
            preparation_profile = session.video_profile
            _, _, _, preparation_frames = VIDEO_PROFILES[preparation_profile]
            # Generate roughly half a clip and append its reverse. This keeps the
            # displayed loop short while guaranteeing that its last pose returns
            # to the first pose instead of jumping at the browser loop boundary.
            idle_frames = 8 * max(1, round((preparation_frames - 1) / 16)) + 1

            idle_condition = folder / "character-idle.wav"
            idle_seconds = (idle_frames - 1) / VIDEO_PROFILES[preparation_profile][2]
            idle_condition.write_bytes(silent_wav(idle_seconds + 0.2))
            idle_image_id, idle_audio_id = await asyncio.gather(
                gateway.upload(character), gateway.upload(idle_condition)
            )
            idle_result = await gateway.generate(
                idle_image_id, idle_audio_id,
                "Seamless idle loop of the same character waiting calmly in the same scene. The lips remain "
                "naturally closed with no speaking or mouth articulation. Only subtle breathing and occasional "
                "gentle blinking; the head and body remain nearly still. No gestures, nodding, swaying, camera "
                "movement, scene change, or facial-expression change. Keep the exact same calm expression "
                "throughout. Preserve exact identity and composition. "
                "Finish in the same neutral pose as the first frame for a smooth loop.",
                session.video_seed, preparation_profile, 8, idle_frames,
            )
            idle_raw = folder / "character-idle-raw.mp4"
            await gateway.download(idle_result["result"]["video_url"], idle_raw)
            # The silent idle generation is a better closed-mouth source than the
            # uploaded still when the latter already has parted lips or a smile.
            await self._frame_at(
                idle_raw, folder / "character-neutral.png", max(0.1, idle_seconds - 0.15)
            )
            idle_video = folder / "character-idle.mp4"
            await self._make_ping_pong_loop(idle_raw, idle_video)
            idle_raw.unlink(missing_ok=True)
            session.idle_video_url = f"/api/sessions/{session.id}/idle-video"
            session.idle_video_ready_at = time()
            self.save(session)

            if speech_task is not None:
                wav, _ = await speech_task
                condition = folder / "character-preparation.wav"
                condition.write_bytes(pad_wav(wav, 5.1))
                image_id, audio_id = await asyncio.gather(
                    gateway.upload(character), gateway.upload(condition)
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
                # resolution. Keep both a mild early articulation frame and the
                # wide-open fallback so the UI can switch modes without re-preparing.
                await self._frame_at(raw, folder / "character-speaking-balanced.png", 0.12)
                await self._frame_at(raw, folder / "character-speaking.png", 0.75)
                raw.unlink(missing_ok=True)
            session.character_prepared = True
            session.character_preparation_seconds = round(time() - started_at, 3)
            session.status = SessionStatus.QUEUED
            self.save(session)
        except Exception as exc:
            session.status = SessionStatus.FAILED
            session.error = str(exc)
            self.save(session)
            raise

    async def _run_chat(self, session: NarrationSession, character: Path,
                        narration_text: str | None = None) -> None:
        folder = self.settings.data_dir / session.id
        gateway = GatewayClient(self.settings.gateway_url, self.settings.gateway_preset,
                                self.settings.poll_interval)
        llm = None if narration_text is not None else StreamingChatClient(
            self.settings.llm_url, self.settings.llm_model, self.settings.llm_api_key
        )
        tts_queue: asyncio.Queue[tuple[asyncio.Task, str, float] | None] = asyncio.Queue()
        video_queue: asyncio.Queue[Chunk | None] = asyncio.Queue()
        assistant_parts: list[str] = []
        session.assistant_text = ""
        clip_duration = profile_duration(session.video_profile)

        async def assemble_audio() -> None:
            elapsed = sum(float(item.duration or 0) for item in session.chunks)
            parts: list[SpeechPart] = []
            parts_duration = 0.0
            started_at: float | None = None
            first_of_turn = True

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
                if parts and parts_duration + part_duration > session.target_chunk_seconds:
                    await emit()
                if not parts:
                    started_at = part_started_at
                parts.append(part)
                parts_duration += part_duration
                # Start immediately on a complete sentence, but do not turn an
                # introductory comma clause into its own five-second video.
                complete_sentence = text.rstrip().endswith(("。", "！", "？", "!", "?"))
                if (first_of_turn and complete_sentence) or parts_duration >= session.target_chunk_seconds:
                    await emit()
            await emit()
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
                    "strong": folder / "character-speaking.png",
                    # Backward compatibility for sessions created before the
                    # natural/balanced/strong modes were introduced.
                    "fast": folder / "character-speaking.png",
                }
                selected = candidates.get(session.lip_sync_mode, candidates["natural"])
                return selected if selected.is_file() else character

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
                reference = photoreal_reference() if session.character_mode == "photoreal" else chain_path
                image_id = await image_asset(reference)
                audio_path = folder / f"chunk-{chunk.index:03}.wav"
                condition_audio = folder / f"chunk-{chunk.index:03}-condition.wav"
                audio_id = await gateway.upload(condition_audio)
                actual_profile = generation_profile(session.video_profile, first_video_of_turn)
                actual_steps = 4 if first_video_of_turn else 8
                # Keep photoreal motion reproducible with the selected seed. Standard
                # mode offsets each chunk so chained clips do not repeat the same motion.
                actual_seed = session.video_seed if session.character_mode == "photoreal" else session.video_seed + chunk.index
                actual_modality_scale = (
                    1.3
                    if session.character_mode == "photoreal"
                    and session.lip_sync_mode in {"natural", "balanced", "strong"}
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
                result = await gateway.generate(
                    image_id, audio_id, self._prompt(
                        chunk.text, session.concept, session.character_mode, session.action_level
                    ),
                    actual_seed, actual_profile, actual_steps, actual_frames,
                    actual_modality_scale,
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
                group.create_task(generate_video())
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

    @staticmethod
    def _prompt(text: str, concept: str, character_mode: str = "photoreal",
                action_level: str = "low") -> str:
        setting = concept.strip() or "a calm, clean studio background"
        spoken_text = " ".join(text.split())[:300]
        action_direction = ACTION_DIRECTIONS.get(action_level, ACTION_DIRECTIONS["low"])
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
                f'Scene direction: {setting}. The character says: "{spoken_text}".'
            )
        return (
            f'The character says exactly: "{spoken_text}". '
            "Clearly and continuously articulate every spoken syllable, with visible rhythmic mouth opening "
            "and closing synchronized to the supplied speech audio. The mouth must not remain closed while "
            "speaking. After the supplied speech ends, stop articulating and naturally return the lips to a "
            f"relaxed closed position for the remaining silence. {mouth_rest}"
            "Medium close-up of the same character, "
            "front-facing or three-quarter view. The full "
            "face, lips, teeth, and jaw remain unobstructed and clearly visible. Preserve identity, with subtle "
            f"blinking and breathing, and a stable camera. {action_direction} Scene direction: {setting}."
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
    async def _make_ping_pong_loop(video: Path, target: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-i", str(video),
            "-filter_complex",
            "[0:v]split[forward][backward];"
            "[forward]setpts=PTS-STARTPTS[f];"
            "[backward]reverse,setpts=PTS-STARTPTS[r];"
            "[f][r]concat=n=2:v=1:a=0,format=yuv420p[out]",
            "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(target), stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode or not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError(f"待機ループ動画の加工に失敗しました: {stderr.decode()[-500:]}")
