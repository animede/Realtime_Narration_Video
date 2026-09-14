from __future__ import annotations

from enum import StrEnum
from time import time
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    CHATTING = "chatting"
    SYNTHESIZING = "synthesizing"
    GENERATING = "generating"
    PLAYABLE = "playable"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Chunk(BaseModel):
    index: int
    text: str
    turn_final: bool = False
    status: str = "queued"
    duration: float | None = None
    speech_duration: float | None = None
    timeline_start: float | None = None
    audio_url: str | None = None
    video_url: str | None = None
    generation_seconds: float | None = None
    generated_profile: str | None = None
    generated_steps: int | None = None
    generated_seed: int | None = None
    generated_frames: int | None = None
    audio_modality_scale: float | None = None
    modality_scale: float | None = None
    tts_started_at: float | None = None
    audio_ready_at: float | None = None
    video_started_at: float | None = None
    video_ready_at: float | None = None
    error: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class NarrationSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: SessionStatus = SessionStatus.QUEUED
    text: str
    concept: str = ""
    video_instruction: str = ""
    action_level: str = "low"
    voice_id: int
    video_profile: str = "20fps-hq"
    character_mode: str = "standard"
    lip_sync_mode: str = "natural"
    idle_motion_profile: str = "wide"
    idle_liveliness: str = "lively"
    idle_pool_size: int = 3
    turn_anchor_mode: str = "speaking"
    turn_end_mode: str = "free"
    camera_lock_enabled: bool = False
    video_seed: int = 1004
    video_steps: int = 4
    modality_scale_enabled: bool = False
    ui_language: str = "ja"
    conversation_language: str = "auto"
    target_chunk_seconds: float = 5.0
    startup_buffer_chunks: int = 1
    chunks: list[Chunk] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    assistant_text: str = ""
    character_prepared: bool = False
    idle_video_url: str | None = None
    idle_video_ready_at: float | None = None
    idle_videos: list[str] = Field(default_factory=list)
    idle_pool_next: int = 0
    character_preparation_seconds: float | None = None
    llm_started_at: float | None = None
    llm_first_delta_at: float | None = None
    llm_completed_at: float | None = None
    updated_at: float = Field(default_factory=time)
    created_at: float = Field(default_factory=time)
    error: str | None = None
    cancelled: bool = False
