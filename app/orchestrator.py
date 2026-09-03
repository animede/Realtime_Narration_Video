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
from .tts import join_wavs, pad_wav, synthesize_sentence


SYSTEM_PROMPT = (
    "あなたは音声で応答する親切な日本語アシスタントです。質問へ自然な話し言葉で簡潔に答えてください。"
    "Markdown、箇条書き記号、URLの読み上げは避け、一文を短くしてください。"
)


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

    async def _run_chat(self, session: NarrationSession, character: Path) -> None:
        folder = self.settings.data_dir / session.id
        gateway = GatewayClient(self.settings.gateway_url, self.settings.gateway_preset,
                                self.settings.poll_interval)
        llm = StreamingChatClient(
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
                chunk_duration = clip_duration
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
                elapsed += clip_duration
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
                if parts and parts_duration >= session.target_chunk_seconds * 0.65 and parts_duration + part_duration > 5.0:
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
            character_id = await gateway.upload(character)
            first_video_of_turn = True
            chain_path = character
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
                image_id = (
                    character_id
                    if session.character_mode == "photoreal" or chain_path == character
                    else await gateway.upload(chain_path)
                )
                audio_path = folder / f"chunk-{chunk.index:03}.wav"
                condition_audio = folder / f"chunk-{chunk.index:03}-condition.wav"
                audio_id = await gateway.upload(condition_audio)
                actual_profile = generation_profile(session.video_profile, first_video_of_turn)
                actual_steps = 4 if first_video_of_turn else 8
                # Photoreal tests showed the most consistent articulation with 1004.
                # Audio, spoken text, and chained reference frames still vary per clip.
                actual_seed = 1004 if session.character_mode == "photoreal" else 1000 + chunk.index
                actual_audio_modality_scale = 1.3 if session.character_mode == "photoreal" else 1.0
                _, _, _, profile_frames = VIDEO_PROFILES[actual_profile]
                actual_frames = profile_frames
                chunk.generated_profile = actual_profile
                chunk.generated_steps = actual_steps
                chunk.generated_seed = actual_seed
                chunk.generated_frames = actual_frames
                chunk.audio_modality_scale = actual_audio_modality_scale
                result = await gateway.generate(
                    image_id, audio_id, self._prompt(chunk.text, session.concept, session.character_mode),
                    actual_seed, actual_profile, actual_steps, actual_frames,
                    actual_audio_modality_scale,
                )
                first_video_of_turn = False
                raw = folder / f"chunk-{chunk.index:03}-raw.mp4"
                await gateway.download(result["result"]["video_url"], raw)
                output = folder / f"chunk-{chunk.index:03}.mp4"
                # Keep the full LTX clip. The conditioning copy contains the exact
                # TTS waveform followed only by silence, giving the next generation
                # time to finish without changing the spoken audio.
                await mux_original_audio(raw, condition_audio, output, float(chunk.duration))
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
            session.status = SessionStatus.CHATTING
            session.error = None
            session.llm_started_at = time()
            session.llm_first_delta_at = None
            session.llm_completed_at = None
            self.save(session)

            async def receiver_with_labels() -> None:
                history = [{"role": "system", "content": SYSTEM_PROMPT}]
                history.extend(item.model_dump() for item in session.messages[-20:])
                buffer = ""
                async for delta in llm.stream(history):
                    if session.llm_first_delta_at is None:
                        session.llm_first_delta_at = time()
                    assistant_parts.append(delta)
                    session.assistant_text = "".join(assistant_parts)
                    buffer += delta
                    fragments, buffer = pop_speakable(buffer)
                    for fragment in fragments:
                        task = asyncio.create_task(synthesize_sentence(
                            self.settings.tts_url, session.voice_id, fragment
                        ))
                        tts_queue.put_nowait((task, fragment, time()))
                    self.save(session)
                fragments, _ = pop_speakable(buffer, force=True)
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
    def _prompt(text: str, concept: str, character_mode: str = "photoreal") -> str:
        setting = concept.strip() or "a calm, clean studio background"
        spoken_text = " ".join(text.split())[:300]
        if character_mode == "standard":
            return (
                "Medium close-up of the same character speaking naturally, front-facing or three-quarter view. "
                "The full face and unobstructed mouth stay clearly visible. Natural lip and jaw movement follows "
                "the supplied narration audio; subtle blinking and breathing, stable camera, consistent identity. "
                f'Scene direction: {setting}. The character says: "{spoken_text}".'
            )
        return (
            f'The character says exactly: "{spoken_text}". '
            "Clearly and continuously articulate every spoken syllable, with visible rhythmic mouth opening "
            "and closing synchronized to the supplied speech audio. The mouth must not remain closed while "
            "speaking. Medium close-up of the same character, front-facing or three-quarter view. The full "
            "face, lips, teeth, and jaw remain unobstructed and clearly visible. Preserve identity, with subtle "
            f"blinking and breathing, and a stable camera. Scene direction: {setting}."
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
