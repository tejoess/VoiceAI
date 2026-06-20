"""Configuration catalog endpoints — static data served from in-process cache."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import registry

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Catalog data is static for the lifetime of a server process.
# 10-minute browser/proxy cache avoids redundant round-trips in the UI.
_CACHE = "public, max-age=600, stale-while-revalidate=60"


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


@router.get("")
async def full_catalog() -> JSONResponse:
    """Everything in one round-trip — the frontend bootstraps from this."""
    data = {
        "languages": registry.languages(),
        "voices": registry.voices(),
        "tones": registry.tones(),
        "speaking_styles": registry.speaking_styles(),
        "capabilities": registry.capabilities(),
    }
    return JSONResponse(data, headers={"Cache-Control": _CACHE})
