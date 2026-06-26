"""TTS preview endpoint for agent creation wizard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.data.voices import get_voice
from app.voice import router as voice_router
from app.data.languages import TTSProvider

router = APIRouter(prefix="/tts", tags=["tts"])

_PREVIEW_TEXT_EN = "Hello! I'm your AI voice assistant. How can I help you today?"
_PREVIEW_TEXT_HI = "नमस्ते! मैं आपका AI वॉयस असिस्टेंट हूँ। आज मैं आपकी कैसे मदद कर सकता हूँ?"


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

    provider: TTSProvider = voice["provider"]
    native_voice_id: str = voice["provider_voice_id"]
    default_text = _PREVIEW_TEXT_HI if provider == TTSProvider.SARVAM else _PREVIEW_TEXT_EN
    text = (body.text or default_text).strip()[:300]  # cap preview length

    # Resolve the provider-specific language tag.
    # For Cartesia voices this is always "en".
    # For Sarvam we need the full BCP-47 tag (e.g. "hi-IN"), not just "hi".
    from app.data.languages import get_language
    lang_tag = "en"
    if provider == TTSProvider.SARVAM:
        # Use the first language the voice supports to pick a valid Sarvam tag.
        first_lang = voice["languages"][0] if voice.get("languages") else "hi"
        lang_meta = get_language(first_lang)
        lang_tag = lang_meta["tts_language"] if lang_meta else "hi-IN"

    # Get the singleton TTS client so we know its actual sample rate.
    tts = voice_router.tts_for(provider)
    actual_rate: int = getattr(tts, "_sample_rate", 24000)

    async def generate():
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
            "X-Sample-Rate": str(actual_rate),  # matches actual synthesis rate
            "X-Channels": "1",
            "X-Bit-Depth": "16",
        },
    )
