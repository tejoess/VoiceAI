"""Two-tier cache for agent configs and metadata.

Tier 1: in-process dict (zero network hop) — used on the realtime path so the
agent worker never blocks on Redis while a call is live.
Tier 2: Redis — shared across worker processes and survives a single worker
restart.

Static catalogs (languages, voices, tones) are preloaded into tier 1 at
startup. Agent configs are cached on first use and invalidated on update.
"""

from __future__ import annotations

import time
from typing import Any

import orjson

from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

# Cache key prefixes
AGENT_PREFIX = "cache:agent:"
META_PREFIX = "cache:meta:"

DEFAULT_TTL = 300  # seconds


class _LocalEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: int):
        self.value = value
        self.expires_at = time.monotonic() + ttl if ttl > 0 else 0.0

    @property
    def alive(self) -> bool:
        return self.expires_at == 0.0 or time.monotonic() < self.expires_at


class TwoTierCache:
    def __init__(self) -> None:
        self._local: dict[str, _LocalEntry] = {}

    # ── local-only (preloaded static catalogs) ─────────────────
    def preload(self, key: str, value: Any) -> None:
        """Pin a value in the in-process tier with no expiry."""
        self._local[key] = _LocalEntry(value, ttl=0)

    def get_local(self, key: str) -> Any | None:
        entry = self._local.get(key)
        if entry is None:
            return None
        if not entry.alive:
            self._local.pop(key, None)
            return None
        return entry.value

    # ── two-tier get/set ───────────────────────────────────────
    async def get(self, key: str) -> Any | None:
        local = self.get_local(key)
        if local is not None:
            return local
        try:
            raw = await get_redis().get(key)
        except Exception as exc:  # Redis down → degrade gracefully
            log.warning("cache.redis_get_failed", key=key, error=str(exc))
            return None
        if raw is None:
            return None
        value = orjson.loads(raw)
        self._local[key] = _LocalEntry(value, DEFAULT_TTL)
        return value

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        self._local[key] = _LocalEntry(value, ttl)
        try:
            await get_redis().set(key, orjson.dumps(value), ex=ttl if ttl > 0 else None)
        except Exception as exc:
            log.warning("cache.redis_set_failed", key=key, error=str(exc))

    async def invalidate(self, key: str) -> None:
        self._local.pop(key, None)
        try:
            await get_redis().delete(key)
        except Exception as exc:
            log.warning("cache.redis_del_failed", key=key, error=str(exc))


# Process-wide singleton
cache = TwoTierCache()


def agent_key(agent_id: str) -> str:
    return f"{AGENT_PREFIX}{agent_id}"


def meta_key(name: str) -> str:
    return f"{META_PREFIX}{name}"
