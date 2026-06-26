"""Voice provider routing.

Routing rule (from the spec):
    English            → Cartesia
    Indian languages   → Sarvam AI

The router is the single authority that resolves an *active language* + a
configured platform ``voice_id`` into a concrete (provider, native voice id,
provider language tag). It cross-checks the selected voice against the language
so a misconfiguration (e.g. an English-only Cartesia voice on a Tamil call) is
auto-corrected to a valid voice for the correct provider instead of failing
mid-call.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.data import voices as voice_data
from app.data.languages import TTSProvider, get_language
from app.data.voices import DEFAULT_VOICE
from app.voice.providers.cartesia import CartesiaTTS
from app.voice.providers.sarvam import SarvamTTS

log = get_logger(__name__)

# Sensible default native voices per provider when the configured voice can't
# serve the active language.
_FALLBACK_NATIVE = {
    TTSProvider.CARTESIA: voice_data.get_voice("cartesia_cindy")["provider_voice_id"],
    TTSProvider.SARVAM: voice_data.get_voice("sarvam_anushka")["provider_voice_id"],
}


@dataclass
class TTSRoute:
    provider: TTSProvider
    native_voice_id: str
    language_tag: str  # provider-specific (e.g. "en", "hi-IN")


def resolve_route(active_language: str, voice_id: str | None) -> TTSRoute:
    lang = get_language(active_language) or get_language("en")
    voice = voice_data.get_voice(voice_id or DEFAULT_VOICE)

    # Provider comes from the selected voice, not the language.
    # This lets users pick Sarvam voices for English calls (Indian accent).
    if voice:
        provider = voice["provider"]
        native = voice["provider_voice_id"]
    else:
        provider = lang["tts_provider"]
        native = _FALLBACK_NATIVE[provider]

    # Language tag must match the TTS provider's expected format.
    if provider == TTSProvider.SARVAM:
        if lang["tts_provider"] == TTSProvider.SARVAM:
            language_tag = lang["tts_language"]   # already hi-IN, ta-IN, etc.
        else:
            # English with a Sarvam voice → en-IN (Sarvam doesn't accept bare "en")
            language_tag = "en-IN"
    else:
        language_tag = lang["tts_language"]        # "en" for Cartesia

    return TTSRoute(provider=provider, native_voice_id=native, language_tag=language_tag)


# ── Cached client singletons (connection pools stay warm) ──────
_cartesia: CartesiaTTS | None = None
_sarvam: SarvamTTS | None = None


def cartesia() -> CartesiaTTS:
    global _cartesia
    if _cartesia is None:
        _cartesia = CartesiaTTS()
    return _cartesia


def sarvam() -> SarvamTTS:
    global _sarvam
    if _sarvam is None:
        _sarvam = SarvamTTS()
    return _sarvam


def tts_for(provider: TTSProvider):
    return cartesia() if provider == TTSProvider.CARTESIA else sarvam()
