from __future__ import annotations

import asyncio
from pathlib import Path


async def mux_original_audio(video: Path, audio: Path, output: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-avoid_negative_ts", "make_zero", str(output),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(f"音声差し替えに失敗しました: {stderr.decode()[-700:]}")
