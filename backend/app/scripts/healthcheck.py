"""End-to-end environment diagnostic.

Run: ``python -m app.scripts.healthcheck``

Live-checks the database, Redis, and every configured provider (Deepgram,
OpenAI, Cartesia, Sarvam, LiveKit) with the smallest possible request, then
prints a PASS/FAIL table. Use this after editing ``.env`` to confirm a real
voice call will work before launching the worker.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.database import dispose_engine, get_sessionmaker, init_engine
from app.core.redis import close_redis, get_redis, init_redis

OK = "PASS"
NO = "FAIL"
SKIP = "skip"


def line(name: str, status: str, detail: str = "") -> None:
    mark = {"PASS": "[ok]  ", "FAIL": "[FAIL]", "skip": "[--]  "}[status]
    print(f"  {mark} {name:<12} {detail}")


async def check_db() -> None:
    from sqlalchemy import text

    try:
        init_engine()
        sm = get_sessionmaker()
        async with sm() as db:
            await db.execute(text("SELECT 1"))
        line("postgres", OK, "connected")
    except Exception as exc:  # noqa: BLE001
        line("postgres", NO, str(exc)[:140])


async def check_redis() -> None:
    if not settings.redis_url:
        line("redis", SKIP, "no REDIS_URL")
        return
    try:
        init_redis()
        await get_redis().ping()
        line("redis", OK, "ping ok")
    except Exception as exc:  # noqa: BLE001
        line("redis", NO, str(exc)[:140])


async def check_openai() -> None:
    if not settings.openai_api_key:
        line("openai", SKIP, "no key")
        return
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        models = await client.models.list()
        ids = {m.id for m in models.data}
        has = settings.openai_model in ids
        line("openai", OK, f"{len(ids)} models; '{settings.openai_model}' {'available' if has else 'NOT found'}")
    except Exception as exc:  # noqa: BLE001
        line("openai", NO, str(exc)[:140])


async def check_deepgram() -> None:
    if not settings.deepgram_api_key:
        line("deepgram", SKIP, "no key")
        return
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            )
        if r.status_code == 200:
            n = len(r.json().get("projects", []))
            line("deepgram", OK, f"key valid, {n} project(s)")
        else:
            line("deepgram", NO, f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as exc:  # noqa: BLE001
        line("deepgram", NO, str(exc)[:140])


async def check_cartesia() -> None:
    if not settings.cartesia_api_key:
        line("cartesia", SKIP, "no key")
        return
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://api.cartesia.ai/voices",
                headers={
                    "X-API-Key": settings.cartesia_api_key,
                    "Cartesia-Version": settings.cartesia_version,
                },
            )
        if r.status_code == 200:
            line("cartesia", OK, "key valid (voices listed)")
        else:
            line("cartesia", NO, f"HTTP {r.status_code}: {r.text[:100]}")
    except Exception as exc:  # noqa: BLE001
        line("cartesia", NO, str(exc)[:140])


async def check_sarvam() -> None:
    if not settings.sarvam_api_key:
        line("sarvam", SKIP, "no key")
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"api-subscription-key": settings.sarvam_api_key},
                json={
                    "inputs": ["नमस्ते"],
                    "target_language_code": "hi-IN",
                    "speaker": "anushka",
                    "model": "bulbul:v2",
                    "speech_sample_rate": 24000,
                },
            )
        if r.status_code == 200 and r.json().get("audios"):
            line("sarvam", OK, "key valid (synthesized 1 clip)")
        else:
            line("sarvam", NO, f"HTTP {r.status_code}: {r.text[:120]}")
    except Exception as exc:  # noqa: BLE001
        line("sarvam", NO, str(exc)[:140])


async def check_livekit() -> None:
    st = settings.provider_status()["livekit"]
    if not st:
        line("livekit", SKIP, "keys not all set")
        return
    try:
        from livekit import api

        lk = api.LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        rooms = await lk.room.list_rooms(api.ListRoomsRequest())
        await lk.aclose()
        line("livekit", OK, f"credentials valid ({len(rooms.rooms)} active rooms)")
    except Exception as exc:  # noqa: BLE001
        line("livekit", NO, str(exc)[:140])


async def main() -> None:
    print("\n=== Voice AI Platform — environment health check ===\n")
    print("Configured providers:", settings.provider_status(), "\n")
    await check_db()
    await check_redis()
    await check_openai()
    await check_deepgram()
    await check_cartesia()
    await check_sarvam()
    await check_livekit()
    print()
    await close_redis()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
