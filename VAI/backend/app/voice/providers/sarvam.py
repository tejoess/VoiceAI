"""Sarvam AI Text-to-Speech (Indian languages).

Sarvam's bulbul TTS is a REST endpoint (no socket streaming yet), so we
preserve the "stream, don't wait for the whole reply" guarantee by synthesizing
*per clause*: each clause the LLM finishes is sent immediately and its audio is
yielded before the next clause is ready. A shared ``httpx.AsyncClient`` keeps
the connection pool warm.

Sarvam returns base64 WAV; we strip the header to emit raw PCM s16le matching
the platform sample rate so it plays out on the LiveKit track like Cartesia.
"""

from __future__ import annotations

import base64
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.voice.providers.base import AudioChunk, ProviderError

log = get_logger(__name__)

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
_WAV_HEADER_BYTES = 44

_client: httpx.AsyncClient | None = None


def get_http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=40),
        )
    return _client


async def close_http() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# Sarvam supports a fixed set of output rates; snap to the nearest valid one.
_VALID_RATES = (8000, 16000, 22050, 24000)


def _snap_rate(rate: int) -> int:
    return min(_VALID_RATES, key=lambda r: abs(r - rate))


class SarvamTTS:
    def __init__(self, model: str | None = None, sample_rate: int | None = None):
        self._model = model or settings.sarvam_model
        self._sample_rate = _snap_rate(sample_rate or settings.audio_sample_rate)

    async def synthesize(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
        language: str = "hi-IN",
    ) -> AsyncIterator[AudioChunk]:
        if not settings.sarvam_api_key:
            raise ProviderError("SARVAM_API_KEY is not configured")

        client = get_http()
        headers = {"api-subscription-key": settings.sarvam_api_key}

        async for chunk in text_stream:
            if not chunk.strip():
                continue
            payload = {
                "inputs": [chunk],
                "target_language_code": language,
                "speaker": voice_id,
                "model": self._model,
                "speech_sample_rate": self._sample_rate,
                "enable_preprocessing": True,
            }
            try:
                resp = await client.post(SARVAM_TTS_URL, json=payload, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"sarvam tts failed: {exc}") from exc

            audios = resp.json().get("audios") or []
            for b64 in audios:
                wav = base64.b64decode(b64)
                pcm = wav[_WAV_HEADER_BYTES:] if len(wav) > _WAV_HEADER_BYTES else wav
                yield AudioChunk(data=pcm, sample_rate=self._sample_rate)

        yield AudioChunk(data=b"", sample_rate=self._sample_rate, is_final=True)
