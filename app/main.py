from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from time import time
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .gateway import (
    DEFAULT_H3_PROFILE, ENGINES, H3_FPS, H3_PROFILES, STARTUP_PROFILES, normalize_engine,
)
from .models import ChatMessage, NarrationSession
from .orchestrator import Orchestrator


app = FastAPI(title="Realtime Narration Video", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
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


@app.get("/api/config")
async def engine_config():
    """Engine selection data for the UI (default engine and the H3 profile table)."""
    return {
        "default_engine": normalize_engine(settings.video_engine),
        "engines": list(ENGINES),
        "h3": {
            "fps": H3_FPS,
            "default_profile": (settings.h3_profile if settings.h3_profile in H3_PROFILES
                                else DEFAULT_H3_PROFILE),
            "profiles": {key: {"width": w, "height": h} for key, (w, h) in H3_PROFILES.items()},
            "first_chunk_seconds": settings.h3_first_chunk_seconds,
            "target_chunk_seconds": settings.h3_target_chunk_seconds,
        },
    }


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
    video_profile: str = Form("20fps-4x3-balanced"),
    video_engine: str = Form(settings.video_engine),
    character_mode: str = Form("standard"),
    lip_sync_mode: str = Form("natural"),
    idle_motion_profile: str = Form("wide"),
    idle_liveliness: str = Form("lively"),
    idle_pool_size: int = Form(5),
    h3_anchor_soften: str = Form("none"),
    h3_idle_mode: str = Form("fl2va"),
    turn_anchor_mode: str = Form("speaking"),
    turn_end_mode: str = Form("free"),
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
    if video_engine not in ENGINES:
        raise HTTPException(400, "動画エンジンが不正です")
    if video_engine == "h3":
        # H3: fps は24固定、解像度は H3 専用表。チャンク長は H3 の格子(3.04/5.875s)に
        # 合わせてサーバ設定から決める(フォームの値は使わない)。LTX のプロファイルが
        # 渡されたら H3 の既定プロファイルへ読み替える。
        if video_profile not in H3_PROFILES:
            video_profile = (settings.h3_profile if settings.h3_profile in H3_PROFILES
                             else DEFAULT_H3_PROFILE)
        target_chunk_seconds = settings.h3_target_chunk_seconds
    elif not 3.5 <= target_chunk_seconds <= 5.0:
        raise HTTPException(400, "チャンク目標時間は3.5～5.0秒にしてください")
    if not 1 <= startup_buffer_chunks <= 5:
        raise HTTPException(400, "先読みチャンク数は1～5にしてください")
    if video_engine != "h3" and video_profile not in STARTUP_PROFILES:
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
    if h3_anchor_soften not in {"none", "weak", "medium"}:
        raise HTTPException(400, "発話参照のソフト化は none/weak/medium から選んでください")
    if h3_idle_mode not in {"fl2va", "silent_ref2va"}:
        raise HTTPException(400, "待機の生成方式は fl2va / silent_ref2va から選んでください")
    if not 3 <= idle_pool_size <= 7:
        raise HTTPException(400, "待機動画の本数は3～7にしてください")
    if turn_anchor_mode not in {"speaking", "idle_frame"}:
        raise HTTPException(400, "会話の開始画像設定が不正です")
    if turn_end_mode not in {"free", "return_idle"}:
        raise HTTPException(400, "会話の終了姿勢設定が不正です")
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
        voice_id=voice_id, video_profile=video_profile, video_engine=video_engine,
        character_mode=character_mode, lip_sync_mode=lip_sync_mode,
        idle_motion_profile=idle_motion_profile, idle_liveliness=idle_liveliness,
        idle_pool_size=idle_pool_size, turn_anchor_mode=turn_anchor_mode,
        h3_anchor_soften=h3_anchor_soften,
        h3_idle_mode=h3_idle_mode,
        turn_end_mode=turn_end_mode,
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
    # 待機フレーム連続モード用: フロントがキャプチャした現在の待機フレーム
    # (data:image/png;base64,... 形式)。ターン先頭チャンクの参照画像になる。
    turn_anchor: str | None = None


class SessionSettingsUpdate(BaseModel):
    concept: str | None = None
    video_instruction: str | None = None
    action_level: str | None = None
    lip_sync_mode: str | None = None
    idle_liveliness: str | None = None
    turn_anchor_mode: str | None = None
    turn_end_mode: str | None = None
    camera_lock_enabled: bool | None = None
    conversation_language: str | None = None
    voice_id: int | None = None
    video_seed: int | None = None
    video_steps: int | None = None
    modality_scale_enabled: bool | None = None
    target_chunk_seconds: float | None = None
    startup_buffer_chunks: int | None = None
    # 2026-10-08: 追い生成頻度の運用調整(待機補充と会話の衝突低減)をセッション中に
    # 変えられるようライブ設定化。プールの実体は次の補充/剪定から新しい本数に追従する。
    idle_pool_size: int | None = None
    h3_anchor_soften: str | None = None
    # H3 待機の生成方式(fl2va / silent_ref2va)。切替は次の補充クリップから効く
    # (既存プールはそのまま。すぐ入れ替えたい場合は待機の再生成を使う)。
    h3_idle_mode: str | None = None


@app.patch("/api/sessions/{session_id}/settings", response_model=NarrationSession)
async def update_session_settings(session_id: str, request: SessionSettingsUpdate):
    session = get_session_or_404(session_id)
    values = request.model_dump(exclude_none=True)
    if session.video_engine == "h3":
        # H3 のチャンク長は格子に合わせた固定値(UI からは変更しない)。
        values.pop("target_chunk_seconds", None)
    if "action_level" in values and values["action_level"] not in {"low", "medium", "high"}:
        raise HTTPException(400, "アクション量が不正です")
    if "lip_sync_mode" in values and values["lip_sync_mode"] not in {
        "natural", "balanced", "medium", "medium_strong", "strong", "fast"
    }:
        raise HTTPException(400, "リップシンク設定が不正です")
    if "idle_liveliness" in values and values["idle_liveliness"] not in {"calm", "lively"}:
        raise HTTPException(400, "待機の動き設定が不正です")
    if "turn_anchor_mode" in values and values["turn_anchor_mode"] not in {"speaking", "idle_frame"}:
        raise HTTPException(400, "会話の開始画像設定が不正です")
    if "turn_end_mode" in values and values["turn_end_mode"] not in {"free", "return_idle"}:
        raise HTTPException(400, "会話の終了姿勢設定が不正です")
    if "conversation_language" in values and values["conversation_language"] not in {"auto", "ja", "en"}:
        raise HTTPException(400, "会話言語が不正です")
    if "video_seed" in values and not 0 <= values["video_seed"] <= 2_147_483_647:
        raise HTTPException(400, "seedは0～2147483647で指定してください")
    if "h3_anchor_soften" in values and values["h3_anchor_soften"] not in {"none", "weak", "medium"}:
        raise HTTPException(400, "発話参照のソフト化は none/weak/medium から選んでください")
    if "h3_idle_mode" in values and values["h3_idle_mode"] not in {"fl2va", "silent_ref2va"}:
        raise HTTPException(400, "待機の生成方式は fl2va / silent_ref2va から選んでください")
    if "idle_pool_size" in values and not 3 <= values["idle_pool_size"] <= 7:
        raise HTTPException(400, "待機動画の本数は3〜7で指定してください")
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
    if orchestrator.any_conversation_running():
        raise HTTPException(409, "会話の生成中は待機動画を再生成できません")
    if not session.character_prepared:
        raise HTTPException(400, "先にキャラクターを設定してください")
    try:
        await orchestrator.regenerate_idle(session)
    except Exception as exc:
        if "interrupted" in str(exc):
            raise HTTPException(409, "会話を優先したため待機動画の生成を中断しました") from exc
        raise HTTPException(502, f"待機動画の再生成に失敗しました: {exc}") from exc
    return session


def save_turn_anchor(session, raw: str | None) -> Path | None:
    """フロントがキャプチャした待機フレームをターン参照用に保存する。"""
    if not raw or session.turn_anchor_mode != "idle_frame":
        return None
    prefix = "base64,"
    index = raw.find(prefix)
    payload = raw[index + len(prefix):] if index >= 0 else raw
    if len(payload) > 8_000_000:
        raise HTTPException(400, "開始画像が大きすぎます")
    try:
        data = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(400, "開始画像のデコードに失敗しました") from exc
    target = settings.data_dir / session.id / "turn-anchor.png"
    target.write_bytes(data)
    return target


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
    turn_anchor = save_turn_anchor(session, request.turn_anchor)
    # 進行中のアイドル生成があれば即中断して会話生成を優先する。
    await orchestrator.interrupt_idle(session_id)
    orchestrator.chat(session, character, turn_video_instruction, turn_anchor=turn_anchor)
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
    turn_anchor = save_turn_anchor(session, request.turn_anchor)
    await orchestrator.interrupt_idle(session_id)
    orchestrator.narrate(session, character, text, turn_anchor=turn_anchor)
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


# --- キャラクタープリセット(保存・一覧・復元・削除) --------------------
# ローカル単一ユーザー構成なのでユーザー管理なしのサーバ側保存
# (data/presets/)。復元は保存済みのアイドルプール・アンカーをコピーする
# だけなので再生成ゼロで即時にセッションが立ち上がる。

PRESET_SETTINGS_KEYS = [
    "video_engine", "concept", "video_instruction", "action_level", "voice_id", "video_profile",
    "character_mode", "lip_sync_mode", "idle_motion_profile", "idle_liveliness",
    "idle_pool_size", "h3_anchor_soften", "h3_idle_mode", "turn_anchor_mode", "turn_end_mode", "camera_lock_enabled",
    "video_seed", "video_steps", "modality_scale_enabled",
    "ui_language", "conversation_language", "target_chunk_seconds",
    "startup_buffer_chunks",
]

PRESET_FILE_PATTERNS = [
    "character.*", "character-neutral.png", "character-speaking*.png",
    "character-idle-*.mp4",
    "character-idle-anchor.png",  # H3 の閉口アンカー(復元時は再生成しない)
]


def preset_dir() -> Path:
    folder = settings.data_dir / "presets"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_preset(preset_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", preset_id):
        raise HTTPException(400, "プリセットIDが不正です")
    meta = preset_dir() / preset_id / "preset.json"
    if not meta.is_file():
        raise HTTPException(404, "プリセットが見つかりません")
    return json.loads(meta.read_text(encoding="utf-8"))


class PresetCreateRequest(BaseModel):
    session_id: str
    name: str | None = None


@app.post("/api/presets")
async def create_preset(request: PresetCreateRequest):
    session = get_session_or_404(request.session_id)
    if not session.character_prepared:
        raise HTTPException(400, "先にキャラクターを設定してください")
    source = settings.data_dir / session.id
    preset_id = uuid4().hex
    target = preset_dir() / preset_id
    target.mkdir(parents=True)
    copied: list[str] = []
    for pattern in PRESET_FILE_PATTERNS:
        for path in sorted(source.glob(pattern)):
            shutil.copyfile(path, target / path.name)
            copied.append(path.name)
    indices = sorted(int(url.rsplit("/", 1)[1]) for url in session.idle_videos)
    meta = {
        "id": preset_id,
        "name": (request.name or "").strip() or datetime.now().strftime("キャラクター %m/%d %H:%M"),
        "created_at": time(),
        "settings": {key: getattr(session, key) for key in PRESET_SETTINGS_KEYS},
        "idle_indices": indices,
        "files": copied,
    }
    (target / "preset.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


@app.get("/api/presets")
async def list_presets(engine: str | None = None):
    """Saved characters. Presets are per engine (an LTX idle pool is not valid for H3):
    pass `engine` to list only that engine's presets (default: all, each tagged)."""
    presets = []
    for meta_path in preset_dir().glob("*/preset.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        preset_engine = meta.get("settings", {}).get("video_engine", "ltx25")
        if engine is not None and preset_engine != engine:
            continue
        presets.append({
            "id": meta["id"], "name": meta.get("name", ""),
            "video_engine": preset_engine,
            "created_at": meta.get("created_at", 0),
            "thumbnail_url": f"/api/presets/{meta['id']}/thumbnail",
            "video_profile": meta.get("settings", {}).get("video_profile", ""),
        })
    presets.sort(key=lambda item: item["created_at"], reverse=True)
    return presets


@app.get("/api/presets/{preset_id}/thumbnail")
async def preset_thumbnail(preset_id: str):
    load_preset(preset_id)
    folder = preset_dir() / preset_id
    image = next(iter(folder.glob("character.*")), None)
    if image is None:
        raise HTTPException(404, "サムネイルが見つかりません")
    return FileResponse(image)


@app.delete("/api/presets/{preset_id}", status_code=204)
async def delete_preset(preset_id: str):
    load_preset(preset_id)
    shutil.rmtree(preset_dir() / preset_id, ignore_errors=True)


@app.post("/api/presets/{preset_id}/restore", response_model=NarrationSession)
async def restore_preset(preset_id: str):
    """保存済みキャラクターから再生成ゼロでセッションを立ち上げる。"""
    meta = load_preset(preset_id)
    source = preset_dir() / preset_id
    session = NarrationSession(text="", **meta["settings"])
    folder = settings.data_dir / session.id
    folder.mkdir(parents=True, exist_ok=True)
    for name in meta.get("files", []):
        src = source / name
        if src.is_file():
            shutil.copyfile(src, folder / name)
    session.character_prepared = True
    indices = meta.get("idle_indices", [])
    session.idle_videos = [f"/api/sessions/{session.id}/idle-video/{i}" for i in indices]
    session.idle_pool_next = (max(indices) + 1) if indices else 0
    if session.idle_videos:
        session.idle_video_url = session.idle_videos[-1]
        session.idle_video_ready_at = time()
    session.status = "queued"
    orchestrator.save(session)
    orchestrator.register(session)
    # The preset keeps its own engine; an H3 preset starts its process and warms ref2va
    # in the background so the first turn does not pay the load + compile.
    orchestrator.start_h3_warmup(session)
    return session


# セッションごとのSSE視聴者数。ブラウザが閉じられた(=視聴者ゼロが続く)のに
# 長文ターンの生成がGPUを走らせ続ける事故を防ぐ(2026-09-14 実測報告)。
sse_watchers: dict[str, int] = {}


async def _cancel_if_abandoned(session_id: str) -> None:
    """視聴者ゼロが5秒続いたら実行中のターンをキャンセルする。

    リロードの瞬断は5秒の猶予で保護される(再接続すればカウントが戻る)。
    キャンセルは既存のチャンク境界チェックで効き、現在のチャンク完了後
    (最大~5秒)に生成が止まる。
    """
    await asyncio.sleep(5)
    if sse_watchers.get(session_id, 0) > 0:
        return
    if not orchestrator.is_running(session_id):
        return
    session = orchestrator.sessions.get(session_id)
    if session is not None and not session.cancelled:
        session.cancelled = True
        orchestrator.save(session)


@app.get("/api/sessions/{session_id}/events")
async def session_events(session_id: str):
    get_session_or_404(session_id)

    async def events():
        previous = ""
        sse_watchers[session_id] = sse_watchers.get(session_id, 0) + 1
        try:
            while True:
                payload = get_session_or_404(session_id).model_dump_json()
                if payload != previous:
                    yield f"event: session\ndata: {payload}\n\n"
                    previous = payload
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.25)
        finally:
            sse_watchers[session_id] = max(0, sse_watchers.get(session_id, 1) - 1)
            if sse_watchers[session_id] == 0:
                asyncio.create_task(_cancel_if_abandoned(session_id))

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
    folder = settings.data_dir / session.id
    # 互換: プールの最新エントリを返す(旧単一ファイルがあればそれも許容)。
    if session.idle_videos:
        index = int(session.idle_videos[-1].rsplit("/", 1)[1])
        path = folder / f"character-idle-{index:03}.mp4"
    else:
        path = folder / "character-idle.mp4"
    if not path.is_file():
        raise HTTPException(404, "待機動画はまだ完成していません")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/sessions/{session_id}/idle-video/{index}")
async def idle_video_pool(session_id: str, index: int):
    session = get_session_or_404(session_id)
    if not 0 <= index < 100_000:
        raise HTTPException(400, "indexが不正です")
    path = settings.data_dir / session.id / f"character-idle-{index:03}.mp4"
    if not path.is_file():
        raise HTTPException(404, "待機動画はまだ完成していません")
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/sessions/{session_id}/idle-pool", response_model=NarrationSession)
async def extend_idle_pool(session_id: str):
    """再生側の残りが少なくなったときに1本追い足す(フロントが呼ぶ)。"""
    session = get_session_or_404(session_id)
    if not session.character_prepared:
        raise HTTPException(400, "先にキャラクターを設定してください")
    if orchestrator.any_conversation_running():
        raise HTTPException(409, "会話の生成中は待機動画を追加できません")
    try:
        await orchestrator.extend_idle_pool(session)
    except Exception as exc:
        if "interrupted" in str(exc):
            # チャット優先の中断 — フロントは黙って次の周回で再試行する。
            raise HTTPException(409, "会話を優先したため待機動画の生成を中断しました") from exc
        raise HTTPException(502, f"待機動画の追加に失敗しました: {exc}") from exc
    return session


def chunk_file(session_id: str, index: int, suffix: str) -> Path:
    session = get_session_or_404(session_id)
    if index < 0 or index >= len(session.chunks):
        raise HTTPException(404, "チャンクが見つかりません")
    path = settings.data_dir / session_id / f"chunk-{index:03}.{suffix}"
    if not path.is_file():
        raise HTTPException(404, "チャンクはまだ完成していません")
    return path


@app.get("/api/sessions/{session_id}/chunks/{index}/audio")
async def chunk_audio(session_id: str, index: int, download: bool = False):
    path = chunk_file(session_id, index, "wav")
    if download:
        return FileResponse(path, media_type="audio/wav",
                            filename=f"narration_{session_id[:8]}_{index + 1:03}.wav")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/sessions/{session_id}/chunks/{index}/video")
async def chunk_video(session_id: str, index: int, download: bool = False):
    path = chunk_file(session_id, index, "mp4")
    if download:
        return FileResponse(path, media_type="video/mp4",
                            filename=f"narration_{session_id[:8]}_{index + 1:03}.mp4")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/fetch-image")
async def fetch_image(url: str):
    """D&D画像URLの取り込み(他タブのローカルURL・file:// のみ。CORS回避プロキシ)。"""
    import mimetypes
    from urllib.parse import unquote, urlparse

    import httpx
    from fastapi.responses import Response

    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        if not path.is_file():
            raise HTTPException(404, f"ファイルが見つかりません: {path}")
        media = mimetypes.guess_type(str(path))[0] or ""
        if not media.startswith("image/"):
            raise HTTPException(415, "画像ではありません")
        return Response(content=path.read_bytes(), media_type=media)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "localhost", "127.0.0.1", "::1",
    ):
        raise HTTPException(400, "ローカルのURLのみ取得できます")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(502, f"画像の取得に失敗しました: {exc}")
    ctype = resp.headers.get("content-type", "")
    if not ctype.startswith("image/"):
        raise HTTPException(415, "画像ではありません")
    return Response(content=resp.content, media_type=ctype)
