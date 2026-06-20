"""Task enqueue API + handler registry.

A deliberately small Redis-list queue (no extra broker dependency). Producers
call ``enqueue(name, payload)`` from anywhere (including the realtime path);
the worker process pops and dispatches. Swap the transport for Celery/Arq/SQS
later without touching call sites.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import orjson

from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

QUEUE_KEY = "vai:tasks"

TaskHandler = Callable[[dict], Awaitable[None]]
_REGISTRY: dict[str, TaskHandler] = {}


def register(name: str) -> Callable[[TaskHandler], TaskHandler]:
    def deco(fn: TaskHandler) -> TaskHandler:
        _REGISTRY[name] = fn
        return fn
    return deco


def get_registry() -> dict[str, TaskHandler]:
    return _REGISTRY


async def enqueue(name: str, payload: dict) -> None:
    """Push a task. Never raises on the realtime path — logs and drops if Redis
    is unavailable so a flaky queue can't break a live call."""
    try:
        await get_redis().rpush(QUEUE_KEY, orjson.dumps({"name": name, "payload": payload}))
    except Exception as exc:  # noqa: BLE001
        log.warning("tasks.enqueue_failed", task=name, error=str(exc))
