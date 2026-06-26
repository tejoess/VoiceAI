"""Background worker entrypoint: ``python -m app.workers.worker``.

Blocking-pops tasks off the Redis queue and dispatches to registered handlers.
Run one or more of these alongside the API; they share the same queue.
"""

from __future__ import annotations

import asyncio
import signal

import orjson

from app.core.database import init_engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_redis, init_redis
from app.workers import handlers  # noqa: F401  (registers handlers)
from app.workers.tasks import QUEUE_KEY, get_registry

log = get_logger(__name__)

_stop = asyncio.Event()


async def _run() -> None:
    configure_logging()
    init_redis()
    init_engine()
    registry = get_registry()
    redis = get_redis()
    log.info("worker.started", handlers=sorted(registry.keys()))

    while not _stop.is_set():
        try:
            item = await redis.blpop(QUEUE_KEY, timeout=2)
        except Exception as exc:  # noqa: BLE001
            log.warning("worker.pop_failed", error=str(exc))
            await asyncio.sleep(1)
            continue
        if item is None:
            continue
        _, raw = item
        try:
            task = orjson.loads(raw)
            handler = registry.get(task["name"])
            if handler is None:
                log.warning("worker.unknown_task", name=task.get("name"))
                continue
            await handler(task.get("payload", {}))
        except Exception as exc:  # noqa: BLE001
            log.error("worker.task_error", error=str(exc))

    log.info("worker.stopped")


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _signal(*_):
        _stop.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _signal)
        loop.add_signal_handler(signal.SIGTERM, _signal)
    except NotImplementedError:  # Windows
        pass

    loop.run_until_complete(_run())


if __name__ == "__main__":
    main()
