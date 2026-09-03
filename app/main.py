from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .gateway import VIDEO_PROFILES
from .models import ChatMessage, NarrationSession
from .orchestrator import Orchestrator


app = FastAPI(title="Realtime Narration Video", version="0.1.0")
orchestrator = Orchestrator(settings)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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
    voice_id: int = Form(settings.tts_speaker_id),
    video_profile: str = Form("20fps-hq"),
    character_mode: str = Form("standard"),
    target_chunk_seconds: float = Form(settings.target_chunk_seconds),
    startup_buffer_chunks: int = Form(settings.startup_buffer_chunks),
    character: UploadFile = File(...),
):
    cleaned = text.strip()
    if len(cleaned) > 20_000:
        raise HTTPException(400, "テキストは20,000文字以内にしてください")
    if not 3.5 <= target_chunk_seconds <= 5.0:
        raise HTTPException(400, "チャンク目標時間は3.5～5.0秒にしてください")
    if not 1 <= startup_buffer_chunks <= 5:
        raise HTTPException(400, "先読みチャンク数は1～5にしてください")
    if video_profile not in VIDEO_PROFILES:
        raise HTTPException(400, "動画プロファイルが不正です")
    if character_mode not in {"standard", "photoreal"}:
        raise HTTPException(400, "キャラクター種別が不正です")
    session = NarrationSession(
        text=cleaned, concept=concept.strip(), voice_id=voice_id, video_profile=video_profile,
        character_mode=character_mode,
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
    if cleaned:
        session.messages.append(ChatMessage(role="user", content=cleaned))
        orchestrator.chat(session, character_path)
    return session


class ChatRequest(BaseModel):
    text: str


@app.post("/api/sessions/{session_id}/messages", response_model=NarrationSession, status_code=202)
async def send_message(session_id: str, request: ChatRequest):
    session = get_session_or_404(session_id)
    if orchestrator.is_running(session_id):
        raise HTTPException(409, "前の応答を生成中です")
    text = request.text.strip()
    if not text:
        raise HTTPException(400, "メッセージを入力してください")
    if len(text) > 8_000:
        raise HTTPException(400, "メッセージは8,000文字以内にしてください")
    folder = settings.data_dir / session.id
    character = next(iter(folder.glob("character.*")), None)
    if character is None:
        raise HTTPException(404, "キャラクター画像が見つかりません")
    session.text = text
    session.cancelled = False
    session.error = None
    session.messages.append(ChatMessage(role="user", content=text))
    orchestrator.save(session)
    orchestrator.chat(session, character)
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
