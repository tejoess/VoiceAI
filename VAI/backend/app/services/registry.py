"""Configuration registry.

Loads the static catalogs (languages, voices, tones, speaking styles,
capabilities) once at startup and pins them in the in-process cache so the
realtime path and the REST API resolve them with zero I/O.

This is the single place the rest of the app asks "what voices/languages/etc.
do we support?" — keeping provider routing and the UI catalog in sync.
"""

from __future__ import annotations

from app.core.cache import cache, meta_key
from app.core.logging import get_logger
from app.data import (
    capabilities as cap_data,
    languages as lang_data,
    speaking_styles as style_data,
    tones as tone_data,
    voices as voice_data,
)

log = get_logger(__name__)


def _serialize(items: list[dict]) -> list[dict]:
    """Make enum values JSON-safe for cache storage."""
    out = []
    for item in items:
        d = dict(item)
        for k, v in d.items():
            if hasattr(v, "value"):  # Enum → str
                d[k] = v.value
        out.append(d)
    return out


def warm_catalogs() -> None:
    """Preload every static catalog into the in-process cache tier."""
    cache.preload(meta_key("languages"), _serialize(lang_data.list_languages()))
    cache.preload(meta_key("voices"), _serialize(voice_data.list_voices()))
    cache.preload(meta_key("tones"), tone_data.list_tones())
    cache.preload(meta_key("speaking_styles"), style_data.list_styles())
    cache.preload(meta_key("capabilities"), cap_data.list_capabilities())
    log.info(
        "registry.warmed",
        languages=len(lang_data.LANGUAGES),
        voices=len(voice_data.VOICES),
        tones=len(tone_data.TONES),
        styles=len(style_data.SPEAKING_STYLES),
        capabilities=len(cap_data.CAPABILITIES),
    )


# ── Catalog accessors (served from cache) ──────────────────────
def languages() -> list[dict]:
    return cache.get_local(meta_key("languages")) or _serialize(lang_data.list_languages())


def voices() -> list[dict]:
    return cache.get_local(meta_key("voices")) or _serialize(voice_data.list_voices())


def tones() -> list[dict]:
    return cache.get_local(meta_key("tones")) or tone_data.list_tones()


def speaking_styles() -> list[dict]:
    return cache.get_local(meta_key("speaking_styles")) or style_data.list_styles()


def capabilities() -> list[dict]:
    return cache.get_local(meta_key("capabilities")) or cap_data.list_capabilities()


# ── Validation helpers (used by agent create/update) ───────────
def validate_language(code: str) -> bool:
    return code in lang_data.LANGUAGES


def validate_voice(voice_id: str) -> bool:
    return voice_id in voice_data.VOICES


def validate_tone(tone_id: str) -> bool:
    return tone_id in tone_data.TONES


def validate_style(style_id: str) -> bool:
    return style_id in style_data.SPEAKING_STYLES


def validate_capabilities(cap_ids: list[str]) -> list[str]:
    """Return any capability ids that are not recognized."""
    return [c for c in cap_ids if c not in cap_data.CAPABILITIES]
