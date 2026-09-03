import io
import wave

from app.tts import pad_wav


def wav_bytes(seconds: float, rate: int = 16000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(b"\0\0" * round(seconds * rate))
    return output.getvalue()


def test_short_conditioning_audio_is_padded():
    padded = pad_wav(wav_bytes(0.5), 5.1)
    with wave.open(io.BytesIO(padded), "rb") as source:
        assert source.getnframes() / source.getframerate() == 5.1


def test_long_audio_is_unchanged():
    original = wav_bytes(5.2)
    assert pad_wav(original, 5.1) is original
