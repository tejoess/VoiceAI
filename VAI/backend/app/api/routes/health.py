"""Health + readiness, including provider configuration status."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import settings
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.app_env,
        "redis": await ping_redis(),
        "providers": settings.provider_status(),
    }


@router.get("/")
async def root() -> dict:
    return {"service": "voice-ai-platform", "version": __version__, "docs": "/docs"}
