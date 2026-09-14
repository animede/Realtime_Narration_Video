from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

import httpx


class LLMError(RuntimeError):
    pass


def _extend_over_japanese_inflection(buffer: str, cut: int) -> int:
    """Avoid cutting between a Japanese verb stem and its common inflection."""
    tail = buffer[cut:]
    match = re.match(
        r"(?:しているか|している|していますか|しています|してください|"
        r"されている|されますか|される|できていますか|できますか|できる|"
        r"しました|しますか|します|した|して|する|ました|ますか|ません)",
        tail,
    )
    return cut + len(match.group(0)) if match else cut


def _looks_english(text: str) -> bool:
    latin = sum(character.isascii() and character.isalpha() for character in text)
    japanese = sum("\u3040" <= character <= "\u30ff" or "\u4e00" <= character <= "\u9fff"
                   for character in text)
    return latin > japanese * 2


def _ja_clause_cut(buffer: str, min_soft: int, clause_max: int) -> int | None:
    """日本語の節境界を探す。

    - 読点は「直前がひらがな」かつ「直前の区切りから8文字以上」のとき節境界
      (〜であり、/〜し、/〜ですが、)。名詞列挙(内容、口調、瞬き、)は
      項目が短く直前も漢字が多いので対象外になる。
    - コロン系(：:；;)は見出しの区切りとして採用(時刻 10:30 等の数字直後は除く)。
    """
    previous_end = 0
    for match in re.finditer(r"[、，,：:；;]\s*", buffer):
        end = match.end()
        if end > clause_max:
            break
        mark = buffer[match.start()]
        before = buffer[match.start() - 1] if match.start() > 0 else ""
        if mark in "：:；;":
            accept = not before.isdigit()
        else:
            accept = ("\u3041" <= before <= "\u309f"
                      and match.start() - previous_end >= 8)
        if accept and end >= min_soft:
            return end
        previous_end = end
    return None


def pop_speakable(buffer: str, force: bool = False, max_chars: int | None = None,
                  min_soft_chars: int | None = None, tail_guard_chars: int | None = None,
                  language: str = "auto") -> tuple[list[str], str]:
    """Return complete speakable fragments while retaining an unfinished suffix."""
    parts: list[str] = []
    while buffer:
        english = language == "en" or (language == "auto" and _looks_english(buffer))
        effective_max = max_chars if max_chars is not None else (52 if english else 22)
        effective_min_soft = min_soft_chars if min_soft_chars is not None else (12 if english else 6)
        effective_guard = tail_guard_chars if tail_guard_chars is not None else (12 if english else 4)
        # 改行は見出しや段落の区切りなので常に文末扱いにする。
        hard = re.search(r"[。！？!?.]\s*|\n+", buffer)
        soft = re.search(r"[、，,；;：:]\s*", buffer)
        clause_max = 48
        # Japanese question endings such as "ますか。" often arrive just after
        # max_chars.  Wait for a small look-ahead window so a one-character
        # suffix is not emitted as a separate speech/video chunk.
        if english:
            soft_ok = soft is not None and effective_min_soft <= soft.end() <= effective_max
            soft_end = soft.end() if soft_ok else None
        else:
            soft_end = _ja_clause_cut(buffer, effective_min_soft, clause_max)
            soft_ok = soft_end is not None
        if soft_ok and (hard is None or soft_end < hard.end()):
            # A short greeting or introductory clause can start TTS before the
            # rest of the LLM response has arrived.
            cut = soft_end
        elif hard:
            # 文末は窓に関係なく常に分割する(文をまたいで塊になるのを防ぐ)。
            cut = hard.end()
        elif len(buffer) >= effective_max + effective_guard:
            candidates = [buffer.rfind(mark, 0, effective_max + 1) for mark in "、，,；;：:\n"]
            if english:
                candidates.append(buffer.rfind(" ", 0, effective_max + 1))
            cut = max(candidates) + 1
            if cut <= 0:
                # 句読点のない位置でのぶち切りはしない — 文末か読点が届くまで
                # バッファを伸ばして待つ(2026-09-14 ユーザー判断: 不自然な
                # 切れ目より生成待ちの間の方が聞きやすい)。
                if not force:
                    break
                cut = len(buffer)
            if not english:
                cut = _extend_over_japanese_inflection(buffer, cut)
        elif force:
            cut = len(buffer)
        else:
            break
        text, buffer = buffer[:cut].strip(), buffer[cut:].lstrip()
        if text:
            parts.append(text)
    if force and buffer and parts and len(buffer.rstrip("。！？!?.、，,；;：: ")) <= 1:
        parts[-1] += buffer
        buffer = ""
    return parts, buffer


class StreamingChatClient:
    def __init__(self, base_url: str, model: str = "", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def resolve_model(self, client: httpx.AsyncClient) -> str:
        if self.model:
            return self.model
        response = await client.get(f"{self.base_url}/models", headers=self.headers)
        response.raise_for_status()
        models = [str(item.get("id")) for item in response.json().get("data", []) if item.get("id")]
        if not models:
            raise LLMError("LLMサーバーに利用可能なモデルがありません")
        return next((item for item in models if "44b" in item.lower()), models[0])

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=300)) as client:
                model = await self.resolve_model(client)
                body = {"model": model, "messages": messages, "stream": True,
                        "temperature": 0.7, "max_tokens": 1200}
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions",
                    headers=self.headers, json=body,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data = json.loads(payload)
                            delta = data["choices"][0].get("delta", {}).get("content")
                        except (ValueError, KeyError, IndexError, TypeError):
                            continue
                        if delta:
                            yield str(delta)
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemma 4サーバーへの接続に失敗しました: {exc}") from exc
