"""Speaking-style presets.

Style controls delivery: sentence length, pacing, verbosity. On the realtime
path, short sentences matter — the TTS streams sooner and barge-in feels
snappier — so most styles bias toward brevity.
"""

from __future__ import annotations

SPEAKING_STYLES: dict[str, dict] = {
    "concise": {
        "id": "concise",
        "name": "Concise",
        "prompt": (
            "Keep responses short — one or two sentences. Get to the point. "
            "Never monologue; let the caller speak."
        ),
    },
    "conversational": {
        "id": "conversational",
        "name": "Conversational",
        "prompt": (
            "Speak in short, natural turns. Use everyday phrasing and brief "
            "back-channels ('got it', 'sure'). Avoid long paragraphs."
        ),
    },
    "detailed": {
        "id": "detailed",
        "name": "Detailed",
        "prompt": (
            "Provide thorough answers when needed, but break them into short "
            "spoken sentences rather than long run-ons."
        ),
    },
    "persuasive": {
        "id": "persuasive",
        "name": "Persuasive",
        "prompt": (
            "Lead with benefits, stay confident, and guide the caller toward "
            "the next step. Keep each turn short and momentum-building."
        ),
    },
}

DEFAULT_STYLE = "conversational"


def get_style(style_id: str) -> dict | None:
    return SPEAKING_STYLES.get(style_id)


def list_styles() -> list[dict]:
    return list(SPEAKING_STYLES.values())
