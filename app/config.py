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
    cors_origins: str = os.getenv("CORS_ORIGINS", "*").strip()
    # --- 動画エンジン(docs/h3-engine-plan.md) -------------------------------
    # 既定 "ltx25" は従来挙動と完全に同一。"h3" を選ぶとセッション作成時の既定エンジンが
    # MiniMax-H3 ref2va になる(セッションごとに video_engine で上書き可能)。
    video_engine: str = os.getenv("VIDEO_ENGINE", "ltx25").strip().lower()
    h3_gateway_preset: str = os.getenv("H3_GATEWAY_PRESET", "dual-realtime-ref2va").strip()
    h3_gpus: str = os.getenv("H3_GPUS", "0,1").strip()
    # H3 の既定解像度プロファイル(app/gateway.py の H3_PROFILES のキー)。
    # 32GB級は縦352x608、96GB級は縦384x704 等を選ぶ(プラン §3b)。
    h3_profile: str = os.getenv("H3_PROFILE", "h3-portrait-352x640").strip()
    # H3 待機クリップの生成方式の既定("fl2va" / "silent_ref2va")。ref2va-only 系
    # プリセット(単騎 24/32GB)では silent_ref2va を注入する(launcher が設定)。
    # セッションごとに h3_idle_mode で上書き可能。
    h3_idle_mode: str = os.getenv("H3_IDLE_MODE", "fl2va").strip()
    # 先頭チャンク(3.04s=73f)と後続チャンク(5.875s=141f の格子に収まる 5.8s)の目標発話長。
    # 待機(FLF)の端点に「閉口アンカー(無音 ref2va の生成フレーム)」を使うか。
    # 既定 0 = 元画像の原寸切り出しを使う(ユーザー判定 2026-10-07: 生成フレームは
    # 画質がやや荒く、元から閉口のキャラでは利点がない)。唇が開いた画像のキャラで
    # 待機の口開きが目立つ場合のみ 1 にする(閉口アンカー自体は常に生成される —
    # ref2va プリワークを兼ねるため)。
    h3_closed_idle_anchor: bool = os.getenv("H3_CLOSED_IDLE_ANCHOR", "0").strip() == "1"
    # 2026-10-08: 3.0(73f)-> 2.33(56f、17n+5 グリッドの1段下)。初動 -0.7s 前後。
    # 2.34 以上にすると ceil が 57f -> 73f へ切り上がる点に注意(2.33 が 56f の上限)。
    h3_first_chunk_seconds: float = float(os.getenv("H3_FIRST_CHUNK_SECONDS", "2.33"))
    # 初回チャンクを1ランク下の解像度で生成(LTX の startup プロファイル相当)。
    h3_startup_lowres: bool = os.getenv("H3_STARTUP_LOWRES", "1") == "1"
    h3_target_chunk_seconds: float = float(os.getenv("H3_TARGET_CHUNK_SECONDS", "5.8"))


settings = Settings()
