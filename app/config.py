from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    gateway_url: str = os.getenv("GATEWAY_URL", "http://localhost:8630").rstrip("/")
    gateway_preset: str = os.getenv("GATEWAY_PRESET", "nvfp4-fast")
    tts_url: str = os.getenv("TTS_URL", "http://localhost:10101").rstrip("/")
    tts_speaker_id: int = int(os.getenv("TTS_SPEAKER_ID", "888753760"))
    llm_url: str = os.getenv("LLM_URL", "http://localhost:8000/v1").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "").strip()
    llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
    data_dir: Path = Path(os.getenv("NARRATION_DATA", "./data")).resolve()
    target_chunk_seconds: float = float(os.getenv("TARGET_CHUNK_SECONDS", "5.0"))
    startup_buffer_chunks: int = int(os.getenv("STARTUP_BUFFER_CHUNKS", "1"))
    poll_interval: float = float(os.getenv("JOB_POLL_INTERVAL", "0.1"))


settings = Settings()
