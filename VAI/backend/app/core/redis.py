"""Redis connection pool.

A single shared connection pool is created at startup and reused everywhere.
Redis backs the agent-configuration cache, voice/language/prompt metadata
caches, and (later) background-worker queues.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_pool: aioredis.ConnectionPool | None = None
_client: aioredis.Redis | None = None


def init_redis() -> aioredis.Redis:
    """Create the shared Redis client backed by a connection pool. Idempotent."""
    global _pool, _client
    if _client is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
            health_check_interval=30,
        )
        _client = aioredis.Redis(connection_pool=_pool)
    return _client


def get_redis() -> aioredis.Redis:
    if _client is None:
        return init_redis()
    return _client


async def close_redis() -> None:
    global _pool, _client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


async def ping_redis() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
