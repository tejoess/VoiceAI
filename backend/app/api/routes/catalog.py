"""Configuration catalog endpoints — static data served from in-process cache."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import registry

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Short cache — voice/language catalog changes during development.
_CACHE = "public, max-age=30, stale-while-revalidate=10"


@router.get("/languages")
async def languages() -> JSONResponse:
    return JSONResponse(registry.languages(), headers={"Cache-Control": _CACHE})


@router.get("/voices")
async def voices() -> JSONResponse:
    return JSONResponse(registry.voices(), headers={"Cache-Control": _CACHE})


@router.get("/tones")
async def tones() -> JSONResponse:
    return JSONResponse(registry.tones(), headers={"Cache-Control": _CACHE})


@router.get("/speaking-styles")
async def speaking_styles() -> JSONResponse:
    return JSONResponse(registry.speaking_styles(), headers={"Cache-Control": _CACHE})


@router.get("/capabilities")
async def capabilities() -> JSONResponse:
    return JSONResponse(registry.capabilities(), headers={"Cache-Control": _CACHE})


_STT_PROVIDERS = [
    {
        "id": "deepgram",
        "name": "Deepgram Nova-2",
        "description": "Real-time streaming STT with interim results and barge-in detection. Best for low latency.",
    },
    {
        "id": "sarvam",
        "name": "Sarvam Saarika v2",
        "description": "Indian-language-optimized batch STT with energy-based VAD. Best for Hindi/Hinglish accuracy.",
    },
]


@router.get("/stt-providers")
async def stt_providers() -> JSONResponse:
    return JSONResponse(_STT_PROVIDERS, headers={"Cache-Control": _CACHE})


@router.get("")
async def full_catalog() -> JSONResponse:
    """Everything in one round-trip — the frontend bootstraps from this."""
    data = {
        "languages": registry.languages(),
        "voices": registry.voices(),
        "tones": registry.tones(),
        "speaking_styles": registry.speaking_styles(),
        "capabilities": registry.capabilities(),
        "stt_providers": _STT_PROVIDERS,
    }
    return JSONResponse(data, headers={"Cache-Control": _CACHE})
