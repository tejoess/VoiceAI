"""Voice catalog.

All Cartesia voice IDs are verified against the live API (2025-06).
Use ``python -m app.tools.sync_voices`` to refresh.
"""

from __future__ import annotations

from app.data.languages import TTSProvider

VOICES: dict[str, dict] = {
    # ── Cartesia – Female (English) ────────────────────────────────────────
    "cartesia_cindy": {
        "id": "cartesia_cindy",
        "name": "Cindy",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "f039066f-cdb7-45ed-b51d-1034ae2f04a0",
        "gender": "female",
        "languages": ["en"],
        "description": "Smooth, welcoming receptionist voice — ideal for front-desk and inbound flows.",
    },
    "cartesia_amber": {
        "id": "cartesia_amber",
        "name": "Amber",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "a7a59115-2425-4192-844c-1e98ec7d6877",
        "gender": "female",
        "languages": ["en"],
        "description": "Cheerful, warm support voice — great for customer service.",
    },
    "cartesia_emily": {
        "id": "cartesia_emily",
        "name": "Emily",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "f6ce3444-478b-4ce4-982e-bcb72dffe7aa",
        "gender": "female",
        "languages": ["en"],
        "description": "Easygoing, friendly and welcoming — perfect for appointment booking.",
    },
    "cartesia_linda": {
        "id": "cartesia_linda",
        "name": "Linda",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "829ccd10-f8b3-43cd-b8a0-4aeaa81f3b30",
        "gender": "female",
        "languages": ["en"],
        "description": "Clear, confident and mature — excellent for professional guidance.",
    },
    "cartesia_ellen": {
        "id": "cartesia_ellen",
        "name": "Ellen",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "5c9e800f-2a92-4720-969b-99c4ab8fbc87",
        "gender": "female",
        "languages": ["en"],
        "description": "Authentic, balanced warmth — great for both casual and formal calls.",
    },
    "cartesia_vicky": {
        "id": "cartesia_vicky",
        "name": "Vicky",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "643f5eee-459d-4b41-b4fc-0b8407139be6",
        "gender": "female",
        "languages": ["en"],
        "description": "Crisp, precise businesswoman — ideal for enterprise and B2B agents.",
    },

    # ── Cartesia – Male (English) ──────────────────────────────────────────
    "cartesia_kurt": {
        "id": "cartesia_kurt",
        "name": "Kurt",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "efa653e5-314d-46ca-9f90-70ac7d6ca71e",
        "gender": "male",
        "languages": ["en"],
        "description": "Expressive, naturally warm — purpose-built for phone support.",
    },
    "cartesia_grant": {
        "id": "cartesia_grant",
        "name": "Grant",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "d46abd1d-2d02-43e8-819f-51fb652c1c61",
        "gender": "male",
        "languages": ["en"],
        "description": "Reliable, neutral American accent — great for customer support.",
    },
    "cartesia_tyler": {
        "id": "cartesia_tyler",
        "name": "Tyler",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "820a3788-2b37-4d21-847a-b65d8a68c99a",
        "gender": "male",
        "languages": ["en"],
        "description": "Direct, confidence-inspiring salesman voice.",
    },
    "cartesia_devansh": {
        "id": "cartesia_devansh",
        "name": "Devansh",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "1259b7e3-cb8a-43df-9446-30971a46b8b0",
        "gender": "male",
        "languages": ["en"],
        "description": "Warm Indian-accented male — natural for Indian-market support.",
    },

    # ── Cartesia – Indian accent (English) ────────────────────────────────
    "cartesia_simi": {
        "id": "cartesia_simi",
        "name": "Simi",
        "provider": TTSProvider.CARTESIA,
        "provider_voice_id": "3b554273-4299-48b9-9aaf-eefd438e3941",
        "gender": "female",
        "languages": ["en"],
        "description": "Firm, young Indian-accented female — excellent for support desks.",
    },

    # ── Sarvam (Indian languages) ─────────────────────────────────────────
    "sarvam_anushka": {
        "id": "sarvam_anushka",
        "name": "Anushka",
        "provider": TTSProvider.SARVAM,
        "provider_voice_id": "anushka",
        "gender": "female",
        "languages": ["hi", "hinglish", "mr", "gu", "ta", "te", "kn", "ml", "bn"],
        "description": "Natural female speaker across all supported Indian languages.",
    },
    "sarvam_abhilash": {
        "id": "sarvam_abhilash",
        "name": "Abhilash",
        "provider": TTSProvider.SARVAM,
        "provider_voice_id": "abhilash",
        "gender": "male",
        "languages": ["hi", "hinglish", "mr", "gu", "ta", "te", "kn", "ml", "bn"],
        "description": "Confident male speaker across all supported Indian languages.",
    },
    "sarvam_manisha": {
        "id": "sarvam_manisha",
        "name": "Manisha",
        "provider": TTSProvider.SARVAM,
        "provider_voice_id": "manisha",
        "gender": "female",
        "languages": ["hi", "hinglish", "mr", "gu", "ta", "te", "kn", "ml", "bn"],
        "description": "Soft, empathetic female speaker — good for healthcare.",
    },
}

DEFAULT_VOICE = "cartesia_cindy"


def get_voice(voice_id: str) -> dict | None:
    return VOICES.get(voice_id)


def list_voices() -> list[dict]:
    return list(VOICES.values())


def voices_for_language(language_code: str) -> list[dict]:
    return [v for v in VOICES.values() if language_code in v["languages"]]
