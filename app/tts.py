from __future__ import annotations

import io
import wave

import httpx


class TTSError(RuntimeError):
    pass


async def synthesize_sentence(base_url: str, speaker: int, text: str) -> tuple[bytes, float]:
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            query = await client.post(f"{base_url}/audio_query", params={"text": text, "speaker": speaker})
            query.raise_for_status()
            query_body = query.json()
            # Keep even a 16-character streaming fragment within the five-second
            # LTX window while retaining natural intelligibility.
            query_body["speedScale"] = max(1.15, float(query_body.get("speedScale", 1.0)))
            response = await client.post(
                f"{base_url}/synthesis", params={"speaker": speaker}, json=query_body
            )
            response.raise_for_status()
        with wave.open(io.BytesIO(response.content), "rb") as source:
            duration = source.getnframes() / source.getframerate()
        return response.content, duration
    except (httpx.HTTPError, ValueError, wave.Error, EOFError) as exc:
        raise TTSError(f"TTS音声合成に失敗しました: {exc}") from exc


def join_wavs(items: list[bytes]) -> bytes:
    output = io.BytesIO()
    params: tuple[int, int, int] | None = None
    frames: list[bytes] = []
    for item in items:
        with wave.open(io.BytesIO(item), "rb") as source:
            current = (source.getnchannels(), source.getsampwidth(), source.getframerate())
            if params is not None and current != params:
                raise TTSError("TTS音声形式がチャンク内で一致しません")
            params = current
            frames.append(source.readframes(source.getnframes()))
    if params is None:
        raise TTSError("結合する音声がありません")
    with wave.open(output, "wb") as target:
        target.setnchannels(params[0])
        target.setsampwidth(params[1])
        target.setframerate(params[2])
        for frame in frames:
            target.writeframes(frame)
    return output.getvalue()


def pad_wav(item: bytes, minimum_seconds: float = 5.1) -> bytes:
    """Pad only the model-conditioning copy; the original narration stays untouched."""
    with wave.open(io.BytesIO(item), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
        missing = max(0, round(minimum_seconds * rate) - source.getnframes())
    if missing == 0:
        return item
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(frames)
        target.writeframes(b"\0" * missing * channels * width)
    return output.getvalue()
