from __future__ import annotations

from enum import StrEnum
from time import time
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    QUEUED = "queued"
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
    voice_id: int
    video_profile: str = "20fps-hq"
    character_mode: str = "standard"
    target_chunk_seconds: float = 5.0
    startup_buffer_chunks: int = 1
    chunks: list[Chunk] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    assistant_text: str = ""
    llm_started_at: float | None = None
    llm_first_delta_at: float | None = None
    llm_completed_at: float | None = None
    updated_at: float = Field(default_factory=time)
    created_at: float = Field(default_factory=time)
    error: str | None = None
    cancelled: bool = False
