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
    provider: TTSProvider = lang["tts_provider"]
    language_tag: str = lang["tts_language"]

    voice = voice_data.get_voice(voice_id or DEFAULT_VOICE)

    # If the configured voice belongs to the right provider AND supports the
    # language, use it. Otherwise fall back to a valid native voice.
    if (
        voice
        and voice["provider"] == provider
        and active_language in voice["languages"]
    ):
        native = voice["provider_voice_id"]
    else:
        native = _FALLBACK_NATIVE[provider]
        if voice_id:
            log.info(
                "router.voice_fallback",
                requested=voice_id,
                language=active_language,
                provider=provider.value,
            )

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
