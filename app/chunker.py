from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SpeechPart:
    text: str
    wav: bytes
    duration: float


def split_sentences(text: str, max_chars: int = 48) -> list[str]:
    """文末・読点でのみ分割する。

    句読点のない位置での文字数ぶち切りはしない(不自然な切れ目は、
    生成待ちの小さな間より聞き苦しい — 2026-09-14 ユーザー判断)。読点も
    ない長文はそのまま1パートにする。5秒を超える発話は既存の
    「映像は最終フレーム静止・音声は最後まで再生」機構が受け止める。
    """
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r", "\n")).strip()
    raw = re.split(r"(?<=[。！？!?])(?:[\u3000 \t]*|\n+)|\n+", normalized)
    result: list[str] = []
    for sentence in (item.strip() for item in raw if item.strip()):
        while len(sentence) > max_chars:
            candidates = [sentence.rfind(mark, 0, max_chars + 1) for mark in "、，,；;：:"]
            cut = max(candidates) + 1
            if cut <= 0:
                break  # 句読点が無ければ切らない
            result.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            result.append(sentence)
    if not result:
        raise ValueError("読み上げるテキストがありません")
    return result


def group_parts(parts: list[SpeechPart], target: float = 5.0,
                minimum: float = 3.5, maximum: float = 6.5) -> list[list[SpeechPart]]:
    groups: list[list[SpeechPart]] = []
    current: list[SpeechPart] = []
    duration = 0.0
    for part in parts:
        if current and duration >= minimum and duration + part.duration > maximum:
            groups.append(current)
            current, duration = [], 0.0
        current.append(part)
        duration += part.duration
        if duration >= target:
            groups.append(current)
            current, duration = [], 0.0
    if current:
        if groups and duration < minimum and sum(item.duration for item in groups[-1]) + duration <= maximum:
            groups[-1].extend(current)
        else:
            groups.append(current)
    return groups
