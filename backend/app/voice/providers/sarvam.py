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

# bulbul:v2 supports exactly these 7 speakers (from Sarvam docs).
# All other speakers use bulbul:v3.
_V2_SPEAKERS = frozenset({
    "anushka", "manisha", "vidya", "arya",   # female
    "abhilash", "karun", "hitesh",            # male
})

# Unicode script ranges → Sarvam BCP-47 language code.
# Used to auto-detect the correct language when the LLM switches script mid-turn.
_DEVANAGARI_CODES = frozenset({"hi-IN", "mr-IN"})   # both use Devanagari
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "hi-IN"),  # Devanagari (Hindi / Marathi — disambiguated below)
    (0x0980, 0x09FF, "bn-IN"),  # Bengali
    (0x0A00, 0x0A7F, "pa-IN"),  # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF, "gu-IN"),  # Gujarati
    (0x0B00, 0x0B7F, "od-IN"),  # Odia
    (0x0B80, 0x0BFF, "ta-IN"),  # Tamil
    (0x0C00, 0x0C7F, "te-IN"),  # Telugu
    (0x0C80, 0x0CFF, "kn-IN"),  # Kannada
    (0x0D00, 0x0D7F, "ml-IN"),  # Malayalam
]


def _detect_language(text: str, configured: str) -> str:
    """Return the Sarvam language code that matches the dominant script in *text*.

    Falls back to *configured* when text is primarily Latin / ASCII.
    Devanagari is ambiguous between Hindi and Marathi: if *configured* is already
    a Devanagari language (hi-IN / mr-IN) we keep it; otherwise default to hi-IN.
    """
    if not text:
        return configured
    n = len(text)
    for start, end, lang in _SCRIPT_RANGES:
        cnt = sum(1 for c in text if start <= ord(c) <= end)
        if cnt >= max(1, n * 0.15):          # ≥ 15% of chars in this script
            if lang == "hi-IN" and configured in _DEVANAGARI_CODES:
                return configured            # Preserve mr-IN when Marathi is configured
            return lang
    return configured

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
    def __init__(self, sample_rate: int | None = None):
        self._sample_rate = _snap_rate(sample_rate or settings.audio_sample_rate)

    @staticmethod
    def model_for(speaker: str) -> str:
        """Return the correct Sarvam model for a given speaker name."""
        return "bulbul:v2" if speaker in _V2_SPEAKERS else "bulbul:v3"

    async def synthesize(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
        language: str = "hi-IN",
    ) -> AsyncIterator[AudioChunk]:
        if not settings.sarvam_api_key:
            raise ProviderError("SARVAM_API_KEY is not configured")

        model = self.model_for(voice_id)
        client = get_http()
        headers = {"api-subscription-key": settings.sarvam_api_key}

        first_chunk = True
        async for chunk in text_stream:
            if not chunk.strip():
                continue
            # Auto-detect the script of this chunk so Hindi/Marathi text sent from
            # an English-configured agent still reaches Sarvam with the right language
            # code.  Falls back to the configured language for Latin/ASCII text.
            actual_lang = _detect_language(chunk, language)
            payload = {
                "inputs": [chunk],
                "target_language_code": actual_lang,
                "speaker": voice_id,
                "model": model,
                "speech_sample_rate": self._sample_rate,
                "enable_preprocessing": True,
            }
            if first_chunk:
                log.info("sarvam.tts_request",
                         speaker=voice_id, language=actual_lang,
                         configured_lang=language, model=model)
                first_chunk = False
            try:
                resp = await client.post(SARVAM_TTS_URL, json=payload, headers=headers)
                if not resp.is_success:
                    log.error("sarvam.tts_error", status=resp.status_code,
                              body=resp.text[:500], payload_speaker=voice_id,
                              payload_lang=actual_lang, payload_model=model)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(f"sarvam tts failed: {exc}") from exc

            audios = resp.json().get("audios") or []
            for b64 in audios:
                wav = base64.b64decode(b64)
                pcm = wav[_WAV_HEADER_BYTES:] if len(wav) > _WAV_HEADER_BYTES else wav
                yield AudioChunk(data=pcm, sample_rate=self._sample_rate)

        yield AudioChunk(data=b"", sample_rate=self._sample_rate, is_final=True)
