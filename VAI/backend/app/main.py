"""FastAPI application factory + lifespan warmup.

On startup we warm everything that would otherwise add latency to the first
request/call: DB engine + pool, Redis pool, preloaded prompt templates, the
config registry (languages/voices/tones/styles/capabilities), and an OpenAI
credential check. Provider keys are optional — the app boots without them and
reports availability via /health.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import settings
from app.core.database import create_all, dispose_engine, init_engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis, init_redis
from app.services import registry
from app.voice.providers.openai_llm import warmup as openai_warmup
from app.voice.providers.sarvam import close_http as close_sarvam_http
from app.voice.templates import warm_templates

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("startup.begin", env=settings.app_env, version=__version__)

    # Persistent connections / pools.
    init_engine()
    init_redis()

    # Preload static config into the in-process cache (zero-I/O on hot path).
    warm_templates()
    registry.warm_catalogs()

    # Dev convenience: ensure tables exist. Use Alembic for real migrations.
    if not settings.is_production:
        try:
            await create_all()
        except Exception as exc:  # noqa: BLE001  (DB may be down in pure-frontend dev)
            log.warning("startup.create_all_failed", error=str(exc))

    # Validate provider creds without blocking boot.
    await openai_warmup()

    log.info("startup.ready", providers=settings.provider_status())
    yield

    log.info("shutdown.begin")
    await close_sarvam_http()
    await close_redis()
    await dispose_engine()
    log.info("shutdown.done")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Voice AI Agent Platform",
        version=__version__,
        description="Multilingual Indian voice AI agents — configurable, low-latency, WebRTC-tested.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
