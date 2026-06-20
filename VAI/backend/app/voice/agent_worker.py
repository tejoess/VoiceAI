"""LiveKit agent worker.

Run with:  ``python -m app.voice.agent_worker dev``  (or ``start`` in prod).

The worker registers with LiveKit; when a browser joins a room created by the
``/sessions/connect`` endpoint, LiveKit dispatches a job here. We use the
Agents framework only for worker lifecycle + job dispatch, then do raw
``livekit.rtc`` audio I/O so the streaming pipeline has full control over
partial transcripts and barge-in.

Room naming contract: ``agent_<agent_id>__<suffix>`` — the agent id is parsed
from the room name so the worker knows which configuration to load.
"""

from __future__ import annotations

import asyncio
import uuid

from livekit import rtc
from livekit.agents import JobContext, WorkerOptions, cli

from app.core.config import settings
from app.core.database import get_sessionmaker, init_engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import init_redis
from app.services import agent_service, registry
from app.voice.providers.base import AudioChunk
from app.voice.providers.openai_llm import warmup as openai_warmup
from app.voice.pipeline import VoicePipeline
from app.voice.templates import warm_templates

log = get_logger(__name__)

_OUTPUT_RATE = settings.audio_sample_rate
_INPUT_RATE = 48000  # WebRTC mic default


def _agent_id_from_room(room_name: str) -> uuid.UUID | None:
    # agent_<uuid>__<suffix>
    if not room_name.startswith("agent_"):
        return None
    rest = room_name[len("agent_"):]
    raw = rest.split("__", 1)[0]
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


async def prewarm() -> None:
    """Warm shared services before taking jobs (latency optimization)."""
    configure_logging()
    init_engine()
    init_redis()
    warm_templates()
    registry.warm_catalogs()
    await openai_warmup()
    log.info("worker.prewarmed", providers=settings.provider_status())


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    room = ctx.room
    log.info("worker.job", room=room.name)

    agent_id = _agent_id_from_room(room.name)
    if agent_id is None:
        log.error("worker.no_agent_id", room=room.name)
        return

    sm = get_sessionmaker()
    async with sm() as db:
        runtime_cfg = await agent_service.get_runtime_config(db, agent_id)
    if runtime_cfg is None:
        log.error("worker.agent_not_found", agent_id=str(agent_id))
        return

    # ── Output track ───────────────────────────────────────────
    source = rtc.AudioSource(_OUTPUT_RATE, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent-voice", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )

    async def emit_audio(chunk: AudioChunk) -> None:
        if not chunk.data:
            return
        frame = rtc.AudioFrame(
            data=chunk.data,
            sample_rate=chunk.sample_rate,
            num_channels=1,
            samples_per_channel=len(chunk.data) // 2,
        )
        await source.capture_frame(frame)

    # ── Event sink (transcript/metrics → frontend via data channel) ─
    async def emit_event(name: str, data: dict) -> None:
        try:
            import orjson

            await room.local_participant.publish_data(
                orjson.dumps({"type": name, **data}), reliable=True, topic="agent"
            )
        except Exception:  # noqa: BLE001
            pass

    pipeline = VoicePipeline(
        runtime_cfg,
        emit_audio=emit_audio,
        emit_event=emit_event,
        input_sample_rate=_INPUT_RATE,
    )

    # Wire the end_call tool → LiveKit room disconnect.
    async def _do_end_call() -> None:
        try:
            await room.disconnect()
        except Exception:  # noqa: BLE001
            pass

    pipeline.on_end_call = _do_end_call
    await pipeline.start()

    # ── Input: read the caller's mic audio into the pipeline ───
    track_tasks: list[asyncio.Task] = []
    seen_tracks: set[str] = set()

    async def handle_audio_track(audio_track: rtc.RemoteAudioTrack) -> None:
        log.info("worker.reading_audio", track_sid=audio_track.sid)
        stream = rtc.AudioStream(audio_track, sample_rate=_INPUT_RATE, num_channels=1)
        async for event in stream:
            await pipeline.push_audio(bytes(event.frame.data))

    def start_reading(track: rtc.Track) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO and track.sid not in seen_tracks:
            seen_tracks.add(track.sid)
            track_tasks.append(asyncio.create_task(handle_audio_track(track)))

    @room.on("track_subscribed")
    def _on_track(track, publication, participant):  # noqa: ANN001
        start_reading(track)

    # With auto_subscribe, the caller's mic track is often ALREADY subscribed by
    # the time we get here — the event above would never fire for it. So scan
    # existing participants and start reading any audio track already present.
    for participant in room.remote_participants.values():
        for pub in participant.track_publications.values():
            if pub.track is not None:
                start_reading(pub.track)

    # Greet immediately, then run the STT consume loop until the call ends.
    await pipeline.greet()
    try:
        await pipeline.run()
    finally:
        for t in track_tasks:
            t.cancel()
        await pipeline.aclose()
        log.info("worker.job_done", room=room.name, metrics=pipeline.metrics)


def _prewarm(_proc) -> None:
    """Module-level prewarm hook.

    Must be a top-level function (not a lambda): on Windows the dev watcher
    spawns the worker in a child process and *pickles* the WorkerOptions, and
    lambdas/closures are not picklable.
    """
    asyncio.run(prewarm())


def main() -> None:
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=_prewarm,
            ws_url=settings.livekit_url or None,
            api_key=settings.livekit_api_key or None,
            api_secret=settings.livekit_api_secret or None,
        )
    )


if __name__ == "__main__":
    main()
