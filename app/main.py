from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .gateway import STARTUP_PROFILES
from .models import ChatMessage, NarrationSession
from .orchestrator import Orchestrator


app = FastAPI(title="Realtime Narration Video", version="0.1.0")
orchestrator = Orchestrator(settings)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

LEADING_VIDEO_INSTRUCTION = re.compile(
    r"^\s*[\[［]([^\]\］\r\n]+)[\]］]\s*"
)


def extract_leading_video_instruction(value: str) -> tuple[str, str]:
    """Separate consecutive leading [video directions] from a chat message."""
    remaining = value
    instructions: list[str] = []
    while match := LEADING_VIDEO_INSTRUCTION.match(remaining):
        instruction = " ".join(match.group(1).split())
        if instruction:
            instructions.append(instruction)
        remaining = remaining[match.end():]
    return remaining.strip(), " ".join(instructions)


@app.get("/")
async def index():
    return FileResponse(static_dir / "index.html")


@app.get("/healthz")
async def healthz():
    checks: dict[str, object] = {"app": "ok"}
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            response = await client.get(f"{settings.gateway_url}/api/v1/status")
            checks["gateway"] = "ok" if response.is_success else f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            checks["gateway"] = str(exc)
        try:
            response = await client.get(f"{settings.tts_url}/version")
            checks["tts"] = "ok" if response.is_success else f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            checks["tts"] = str(exc)
        try:
            response = await client.get(f"{settings.llm_url}/models")
            checks["llm"] = "ok" if response.is_success else f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            checks["llm"] = str(exc)
    return checks


@app.post("/api/sessions", response_model=NarrationSession, status_code=202)
async def create_session(
    text: str = Form(""),
    concept: str = Form(""),
    video_instruction: str = Form(""),
    action_level: str = Form("low"),
    voice_id: int = Form(settings.tts_speaker_id),
    video_profile: str = Form("20fps-hq"),
    character_mode: str = Form("standard"),
    lip_sync_mode: str = Form("natural"),
    idle_motion_profile: str = Form("wide"),
    idle_liveliness: str = Form("lively"),
    camera_lock_enabled: bool = Form(False),
    video_seed: int = Form(1004),
    video_steps: int = Form(4),
    modality_scale_enabled: bool = Form(False),
    ui_language: str = Form("ja"),
    conversation_language: str = Form("auto"),
    target_chunk_seconds: float = Form(settings.target_chunk_seconds),
    startup_buffer_chunks: int = Form(settings.startup_buffer_chunks),
    character: UploadFile = File(...),
):
    cleaned = text.strip()
    if len(cleaned) > 20_000:
        raise HTTPException(400, "テキストは20,000文字以内にしてください")
    cleaned_video_instruction = video_instruction.strip()
    if len(cleaned_video_instruction) > 1_000:
        raise HTTPException(400, "動画への指示は1,000文字以内にしてください")
    if not 3.5 <= target_chunk_seconds <= 5.0:
        raise HTTPException(400, "チャンク目標時間は3.5～5.0秒にしてください")
    if not 1 <= startup_buffer_chunks <= 5:
        raise HTTPException(400, "先読みチャンク数は1～5にしてください")
    if video_profile not in STARTUP_PROFILES:
        raise HTTPException(400, "動画プロファイルが不正です")
    if character_mode not in {"standard", "photoreal"}:
        raise HTTPException(400, "キャラクター種別が不正です")
    if action_level not in {"low", "medium", "high"}:
        raise HTTPException(400, "アクション量が不正です")
    if lip_sync_mode not in {"natural", "balanced", "medium", "medium_strong", "strong", "fast"}:
        raise HTTPException(400, "リップシンク設定が不正です")
    if idle_motion_profile not in {"closeup", "upper_body", "wide"}:
        raise HTTPException(400, "アイドル動作設定が不正です")
    if idle_liveliness not in {"calm", "lively"}:
        raise HTTPException(400, "待機の動き設定が不正です")
    if not 0 <= video_seed <= 2_147_483_647:
        raise HTTPException(400, "seedは0～2147483647で指定してください")
    if not 1 <= video_steps <= 12:
        raise HTTPException(400, "stepsは1～12にしてください")
    if ui_language not in {"ja", "en"}:
        raise HTTPException(400, "UI言語が不正です")
    if conversation_language not in {"auto", "ja", "en"}:
        raise HTTPException(400, "会話言語が不正です")
    session = NarrationSession(
        text=cleaned, concept=concept.strip(), video_instruction=cleaned_video_instruction,
        action_level=action_level,
        voice_id=voice_id, video_profile=video_profile,
        character_mode=character_mode, lip_sync_mode=lip_sync_mode,
        idle_motion_profile=idle_motion_profile, idle_liveliness=idle_liveliness,
        camera_lock_enabled=camera_lock_enabled,
        video_seed=video_seed,
        video_steps=video_steps, modality_scale_enabled=modality_scale_enabled,
        ui_language=ui_language, conversation_language=conversation_language,
        target_chunk_seconds=target_chunk_seconds,
        startup_buffer_chunks=startup_buffer_chunks,
    )
    folder = settings.data_dir / session.id
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(character.filename or "character.png").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "キャラクター画像はPNG/JPEG/WebPを使用してください")
    character_path = folder / f"character{suffix}"
    with character_path.open("wb") as output:
        shutil.copyfileobj(character.file, output)
    orchestrator.save(session)
    orchestrator.register(session)
    try:
        await orchestrator.prepare_character(session, character_path)
    except Exception as exc:
        raise HTTPException(502, f"キャラクター準備に失敗しました: {exc}") from exc
    if cleaned:
        session.messages.append(ChatMessage(role="user", content=cleaned))
        orchestrator.chat(session, character_path)
    return session


class ChatRequest(BaseModel):
    text: str


class SessionSettingsUpdate(BaseModel):
    concept: str | None = None
    video_instruction: str | None = None
    action_level: str | None = None
    lip_sync_mode: str | None = None
    idle_liveliness: str | None = None
    camera_lock_enabled: bool | None = None
    conversation_language: str | None = None
    voice_id: int | None = None
    video_seed: int | None = None
    video_steps: int | None = None
    modality_scale_enabled: bool | None = None
    target_chunk_seconds: float | None = None
    startup_buffer_chunks: int | None = None


@app.patch("/api/sessions/{session_id}/settings", response_model=NarrationSession)
async def update_session_settings(session_id: str, request: SessionSettingsUpdate):
    session = get_session_or_404(session_id)
    values = request.model_dump(exclude_none=True)
    if "action_level" in values and values["action_level"] not in {"low", "medium", "high"}:
        raise HTTPException(400, "アクション量が不正です")
    if "lip_sync_mode" in values and values["lip_sync_mode"] not in {
        "natural", "balanced", "medium", "medium_strong", "strong", "fast"
    }:
        raise HTTPException(400, "リップシンク設定が不正です")
    if "idle_liveliness" in values and values["idle_liveliness"] not in {"calm", "lively"}:
        raise HTTPException(400, "待機の動き設定が不正です")
    if "conversation_language" in values and values["conversation_language"] not in {"auto", "ja", "en"}:
        raise HTTPException(400, "会話言語が不正です")
    if "video_seed" in values and not 0 <= values["video_seed"] <= 2_147_483_647:
        raise HTTPException(400, "seedは0～2147483647で指定してください")
    if "video_steps" in values and not 1 <= values["video_steps"] <= 12:
        raise HTTPException(400, "stepsは1～12にしてください")
    if "target_chunk_seconds" in values and not 3.5 <= values["target_chunk_seconds"] <= 5.0:
        raise HTTPException(400, "チャンク目標時間は3.5～5.0秒にしてください")
    if "startup_buffer_chunks" in values and not 1 <= values["startup_buffer_chunks"] <= 5:
        raise HTTPException(400, "先読みチャンク数は1～5にしてください")
    if "video_instruction" in values and len(values["video_instruction"].strip()) > 1_000:
        raise HTTPException(400, "動画への指示は1,000文字以内にしてください")
    if "concept" in values:
        values["concept"] = values["concept"].strip()
    if "video_instruction" in values:
        values["video_instruction"] = values["video_instruction"].strip()
    for name, value in values.items():
        setattr(session, name, value)
    orchestrator.save(session)
    return session


@app.post("/api/sessions/{session_id}/regenerate-idle", response_model=NarrationSession)
async def regenerate_idle(session_id: str):
    session = get_session_or_404(session_id)
    if orchestrator.is_running(session_id):
        raise HTTPException(409, "応答の生成中は待機動画を再生成できません")
    if not session.character_prepared:
        raise HTTPException(400, "先にキャラクターを設定してください")
    try:
        await orchestrator.regenerate_idle(session)
    except Exception as exc:
        raise HTTPException(502, f"待機動画の再生成に失敗しました: {exc}") from exc
    return session


@app.post("/api/sessions/{session_id}/messages", response_model=NarrationSession, status_code=202)
async def send_message(session_id: str, request: ChatRequest):
    session = get_session_or_404(session_id)
    if orchestrator.is_running(session_id):
        raise HTTPException(409, "前の応答を生成中です")
    raw_text = request.text.strip()
    if len(raw_text) > 8_000:
        raise HTTPException(400, "メッセージは8,000文字以内にしてください")
    text, turn_video_instruction = extract_leading_video_instruction(raw_text)
    if not text:
        raise HTTPException(400, "動画指示に続けてメッセージを入力してください")
    if len(turn_video_instruction) > 1_000:
        raise HTTPException(400, "角括弧内の動画指示は合計1,000文字以内にしてください")
    folder = settings.data_dir / session.id
    character = next(iter(folder.glob("character.*")), None)
    if character is None:
        raise HTTPException(404, "キャラクター画像が見つかりません")
    session.text = text
    session.cancelled = False
    session.error = None
    session.messages.append(ChatMessage(role="user", content=text))
    orchestrator.save(session)
    orchestrator.chat(session, character, turn_video_instruction)
    return session


@app.post("/api/sessions/{session_id}/narrations", response_model=NarrationSession, status_code=202)
async def narrate_text(session_id: str, request: ChatRequest):
    session = get_session_or_404(session_id)
    if orchestrator.is_running(session_id):
        raise HTTPException(409, "前の応答を生成中です")
    text = request.text.strip()
    if not text:
        raise HTTPException(400, "朗読する文章を入力してください")
    if len(text) > 20_000:
        raise HTTPException(400, "朗読文章は20,000文字以内にしてください")
    folder = settings.data_dir / session.id
    character = next(iter(folder.glob("character.*")), None)
    if character is None:
        raise HTTPException(404, "キャラクター画像が見つかりません")
    session.text = text
    session.cancelled = False
    session.error = None
    session.assistant_text = ""
    orchestrator.save(session)
    orchestrator.narrate(session, character, text)
    return session


def get_session_or_404(session_id: str) -> NarrationSession:
    session = orchestrator.sessions.get(session_id)
    if session is None:
        path = settings.data_dir / session_id / "session.json"
        if path.is_file():
            try:
                session = NarrationSession.model_validate_json(path.read_text(encoding="utf-8"))
                orchestrator.sessions[session_id] = session
            except (OSError, ValueError):
                session = None
    if session is None:
        raise HTTPException(404, "セッションが見つかりません")
    return session


@app.get("/api/sessions/{session_id}", response_model=NarrationSession)
async def get_session(session_id: str):
    return get_session_or_404(session_id)


@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str):
    get_session_or_404(session_id)

    async def events():
        previous = ""
        while True:
            payload = get_session_or_404(session_id).model_dump_json()
            if payload != previous:
                yield f"event: session\ndata: {payload}\n\n"
                previous = payload
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.delete("/api/sessions/{session_id}", status_code=204)
async def cancel_session(session_id: str):
    session = get_session_or_404(session_id)
    session.cancelled = True
    orchestrator.save(session)


@app.get("/api/sessions/{session_id}/idle-video")
async def idle_video(session_id: str):
    session = get_session_or_404(session_id)
    path = settings.data_dir / session.id / "character-idle.mp4"
    if not path.is_file():
        raise HTTPException(404, "待機動画はまだ完成していません")
    return FileResponse(path, media_type="video/mp4")


def chunk_file(session_id: str, index: int, suffix: str) -> Path:
    session = get_session_or_404(session_id)
    if index < 0 or index >= len(session.chunks):
        raise HTTPException(404, "チャンクが見つかりません")
    path = settings.data_dir / session_id / f"chunk-{index:03}.{suffix}"
    if not path.is_file():
        raise HTTPException(404, "チャンクはまだ完成していません")
    return path


@app.get("/api/sessions/{session_id}/chunks/{index}/audio")
async def chunk_audio(session_id: str, index: int):
    return FileResponse(chunk_file(session_id, index, "wav"), media_type="audio/wav")


@app.get("/api/sessions/{session_id}/chunks/{index}/video")
async def chunk_video(session_id: str, index: int):
    return FileResponse(chunk_file(session_id, index, "mp4"), media_type="video/mp4")
