"""Async SQLAlchemy engine + session management.

Supports both SQLite (local dev, zero setup) and PostgreSQL (staging/prod).

SQLite:   DATABASE_URL=sqlite+aiosqlite:///./vai.db  (default — no Postgres needed)
Postgres: DATABASE_URL=postgresql+asyncpg://...      (Neon, Supabase, local PG, etc.)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def _prepare_url(url: str) -> tuple[str, dict]:
    """Normalize a database URL for its async driver.

    SQLite:   translate ``sqlite://`` → ``sqlite+aiosqlite://`` and add
              ``check_same_thread=False`` so asyncio tasks share the connection.
    Postgres: translate bare ``postgresql://`` → ``postgresql+asyncpg://`` and
              strip libpq params (sslmode, channel_binding) that asyncpg doesn't
              understand, translating ``sslmode`` into asyncpg's ``ssl`` arg.
              Adds a 30-second connect timeout to survive Neon/Supabase cold starts.
    """
    # ── SQLite ──────────────────────────────────────────────────────────────
    if url.startswith("sqlite"):
        if "aiosqlite" not in url:
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url, {"check_same_thread": False}

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
        scheme = "postgresql+asyncpg"
    parts = parts._replace(scheme=scheme)

    connect_args: dict = {
        # 30 s timeout survives Neon/Supabase cold-start (default is ~system TCP timeout)
        "timeout": 30,
    }
    if parts.query:
        q = dict(parse_qsl(parts.query))
        sslmode = q.pop("sslmode", None)
        q.pop("channel_binding", None)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = True
        parts = parts._replace(query=urlencode(q))

    return urlunsplit(parts), connect_args


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    """Create the global engine + sessionmaker. Idempotent."""
    global _engine, _sessionmaker
    if _engine is None:
        url, connect_args = _prepare_url(settings.database_url)
        is_sqlite = url.startswith("sqlite")

        if is_sqlite:
            # Let SQLAlchemy pick the pool automatically for SQLite.
            # StaticPool causes issues with aiosqlite's thread model.
            _engine = create_async_engine(
                url,
                echo=False,
                connect_args=connect_args,
                future=True,
            )
        else:
            _engine = create_async_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_recycle=1800,
                future=True,
                connect_args=connect_args,
            )

        _sessionmaker = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped async session."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    """Create tables from metadata (dev convenience; use Alembic in prod)."""
    from app import models  # noqa: F401

    engine = init_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
