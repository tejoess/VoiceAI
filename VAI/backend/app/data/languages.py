"""Supported languages and their provider routing.

Each language declares:
  - the Deepgram STT language code (for partial-transcript streaming)
  - the TTS provider that should render it (Cartesia for English, Sarvam for
    Indian languages) and the provider-specific language tag
  - a human prompt hint used by the language layer of the prompt builder
"""

from __future__ import annotations

from enum import Enum


class TTSProvider(str, Enum):
    CARTESIA = "cartesia"
    SARVAM = "sarvam"


LANGUAGES: dict[str, dict] = {
    "en": {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "deepgram_code": "en-IN",
        "tts_provider": TTSProvider.CARTESIA,
        "tts_language": "en",
        "prompt_hint": "Respond in clear, natural English.",
        "indian": False,
    },
    "hi": {
        "code": "hi",
        "name": "Hindi",
        "native_name": "हिन्दी",
        "deepgram_code": "hi",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "hi-IN",
        "prompt_hint": "Respond in natural, conversational Hindi (Devanagari script).",
        "indian": True,
    },
    "hinglish": {
        "code": "hinglish",
        "name": "Hinglish",
        "native_name": "Hinglish",
        # Deepgram multi handles code-switched Hindi/English audio best.
        "deepgram_code": "multi",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "hi-IN",
        "prompt_hint": (
            "Respond in Hinglish — natural Hindi-English code-mixing the way "
            "urban Indians speak. Keep common English words in English."
        ),
        "indian": True,
    },
    "mr": {
        "code": "mr",
        "name": "Marathi",
        "native_name": "मराठी",
        "deepgram_code": "mr",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "mr-IN",
        "prompt_hint": "Respond in natural, conversational Marathi.",
        "indian": True,
    },
    "gu": {
        "code": "gu",
        "name": "Gujarati",
        "native_name": "ગુજરાતી",
        "deepgram_code": "gu",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "gu-IN",
        "prompt_hint": "Respond in natural, conversational Gujarati.",
        "indian": True,
    },
    "ta": {
        "code": "ta",
        "name": "Tamil",
        "native_name": "தமிழ்",
        "deepgram_code": "ta",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "ta-IN",
        "prompt_hint": "Respond in natural, conversational Tamil.",
        "indian": True,
    },
    "te": {
        "code": "te",
        "name": "Telugu",
        "native_name": "తెలుగు",
        "deepgram_code": "te",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "te-IN",
        "prompt_hint": "Respond in natural, conversational Telugu.",
        "indian": True,
    },
    "kn": {
        "code": "kn",
        "name": "Kannada",
        "native_name": "ಕನ್ನಡ",
        "deepgram_code": "kn",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "kn-IN",
        "prompt_hint": "Respond in natural, conversational Kannada.",
        "indian": True,
    },
    "ml": {
        "code": "ml",
        "name": "Malayalam",
        "native_name": "മലയാളം",
        "deepgram_code": "ml",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "ml-IN",
        "prompt_hint": "Respond in natural, conversational Malayalam.",
        "indian": True,
    },
    "bn": {
        "code": "bn",
        "name": "Bengali",
        "native_name": "বাংলা",
        "deepgram_code": "bn",
        "tts_provider": TTSProvider.SARVAM,
        "tts_language": "bn-IN",
        "prompt_hint": "Respond in natural, conversational Bengali.",
        "indian": True,
    },
}

DEFAULT_LANGUAGE = "en"


def get_language(code: str) -> dict | None:
    return LANGUAGES.get(code)


def list_languages() -> list[dict]:
    return list(LANGUAGES.values())
