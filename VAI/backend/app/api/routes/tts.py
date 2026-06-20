"""TTS preview endpoint for agent creation wizard."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.data.voices import get_voice
from app.voice import router as voice_router
from app.data.languages import TTSProvider

router = APIRouter(prefix="/tts", tags=["tts"])

_PREVIEW_TEXT = "Hello! I'm your AI voice assistant. How can I help you today?"


class PreviewRequest(BaseModel):
    voice_id: str
    text: str | None = None


@router.post("/preview")
async def preview_voice(body: PreviewRequest):
    """Synthesize a short sample with the requested voice and stream it back.

    Returns raw PCM audio (16-bit signed, little-endian) at 16 000 Hz mono
    wrapped in a streaming response. The frontend can decode with Web Audio API.
    """
    voice = get_voice(body.voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Voice '{body.voice_id}' not found.")

    text = (body.text or _PREVIEW_TEXT).strip()[:300]  # cap preview length
    provider: TTSProvider = voice["provider"]
    native_voice_id: str = voice["provider_voice_id"]

    # Resolve language tag for the voice (use English for all Cartesia voices).
    lang_tag = "en"
    if provider == TTSProvider.SARVAM:
        lang_tag = "hi"  # default to Hindi for Sarvam preview

    async def generate():
        tts = voice_router.tts_for(provider)
        async def _single():
            yield text

        try:
            async for chunk in tts.synthesize(_single(), voice_id=native_voice_id, language=lang_tag):
                if chunk.data:
                    yield chunk.data
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"TTS error: {exc}") from exc

    return StreamingResponse(
        generate(),
        media_type="audio/pcm",
        headers={
            "X-Sample-Rate": "16000",
            "X-Channels": "1",
            "X-Bit-Depth": "16",
        },
    )
