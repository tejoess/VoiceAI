"""Tone presets.

A tone contributes a short instruction block to the Tone layer of the prompt.
Tones are intentionally orthogonal to speaking style: tone shapes *attitude*,
style shapes *delivery / pacing*.
"""

from __future__ import annotations

TONES: dict[str, dict] = {
    "professional": {
        "id": "professional",
        "name": "Professional",
        "prompt": "Maintain a professional, courteous, and composed tone. Be respectful and precise.",
    },
    "friendly": {
        "id": "friendly",
        "name": "Friendly",
        "prompt": "Be warm, friendly, and approachable. Sound like a helpful person who genuinely cares.",
    },
    "empathetic": {
        "id": "empathetic",
        "name": "Empathetic",
        "prompt": "Be empathetic and patient. Acknowledge the caller's feelings before solving their problem.",
    },
    "energetic": {
        "id": "energetic",
        "name": "Energetic",
        "prompt": "Be upbeat, enthusiastic, and positive without being over the top.",
    },
    "formal": {
        "id": "formal",
        "name": "Formal",
        "prompt": "Use a formal register. Avoid slang and contractions. Be deferential and exact.",
    },
    "casual": {
        "id": "casual",
        "name": "Casual",
        "prompt": "Keep it casual and conversational, like chatting with a friend. Contractions are fine.",
    },
}

DEFAULT_TONE = "friendly"


def get_tone(tone_id: str) -> dict | None:
    return TONES.get(tone_id)


def list_tones() -> list[dict]:
    return list(TONES.values())
