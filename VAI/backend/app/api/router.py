"""Aggregate API router mounted under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import agents, analytics, catalog, health, sessions
from app.api.routes import knowledge, tts

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(agents.router)
api_router.include_router(sessions.router)
api_router.include_router(analytics.router)
api_router.include_router(knowledge.router)
api_router.include_router(tts.router)
