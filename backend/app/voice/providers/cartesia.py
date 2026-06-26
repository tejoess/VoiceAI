"""Cartesia streaming Text-to-Speech (English).

Two classes:
  CartesiaTTS           — original per-call WS (used as fallback / for tests)
  CartesiaPersistentWS  — long-lived WS per agent call that REUSES the TCP+TLS
                          connection for every LLM turn, eliminating 300-500ms of
                          WS-connect overhead on every response.

Production path: pipeline.start() connects a CartesiaPersistentWS while STT
is warming up; every _stream_completion call reuses that WS, so first audio
arrives ~300-500ms earlier than with a per-call WS.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import AsyncIterator

import websockets

from app.core.config import settings
from app.core.logging import get_logger
from app.voice.providers.base import AudioChunk, ProviderError

log = get_logger(__name__)

CARTESIA_WS = "wss://api.cartesia.ai/tts/websocket"


def _ws_url() -> str:
    return (
        f"{CARTESIA_WS}"
        f"?api_key={settings.cartesia_api_key}"
        f"&cartesia_version={settings.cartesia_version}"
    )


def _ws_is_open(ws: object) -> bool:
    """Return True if the websocket connection is still open.

    websockets 13+ (ClientConnection) uses .state == State.OPEN.
    websockets < 13 (WebSocketClientProtocol) uses .open / .closed.
    """
    # websockets 13+
    try:
        from websockets.connection import State  # type: ignore[import]
        return ws.state == State.OPEN  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass
    # websockets < 13 fallback
    if hasattr(ws, "open"):
        return bool(ws.open)  # type: ignore[attr-defined]
    return not getattr(ws, "closed", True)


# ── Per-call (legacy / fallback) ───────────────────────────────────────────

class CartesiaTTS:
    """Creates a fresh WebSocket for each synthesis call. Used for tests and
    as fallback when CartesiaPersistentWS is not available."""

    def __init__(self, model: str | None = None, sample_rate: int | None = None):
        self._model = model or settings.cartesia_model
        self._sample_rate = sample_rate or settings.audio_sample_rate

    async def synthesize(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
        language: str = "en",
    ) -> AsyncIterator[AudioChunk]:
        if not settings.cartesia_api_key:
            raise ProviderError("CARTESIA_API_KEY is not configured")

        context_id = uuid.uuid4().hex

        try:
            ws = await websockets.connect(_ws_url(), max_size=None, ping_interval=5)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"cartesia connect failed: {exc}") from exc

        async def _send() -> None:
            def _payload(transcript: str, cont: bool) -> str:
                return json.dumps({
                    "context_id": context_id,
                    "model_id": self._model,
                    "transcript": transcript,
                    "voice": {"mode": "id", "id": voice_id},
                    "language": language,
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": self._sample_rate,
                    },
                    "continue": cont,
                })

            try:
                async for chunk in text_stream:
                    if not chunk:
                        continue
                    await ws.send(_payload(chunk, True))
                await ws.send(_payload("", False))
            except Exception:  # noqa: BLE001
                pass

        send_task = asyncio.create_task(_send())
        try:
            async for raw in ws:
                msg = json.loads(raw)
                mtype = msg.get("type")
                if mtype == "chunk" and msg.get("data"):
                    yield AudioChunk(
                        data=base64.b64decode(msg["data"]),
                        sample_rate=self._sample_rate,
                    )
                elif mtype == "done":
                    yield AudioChunk(data=b"", sample_rate=self._sample_rate, is_final=True)
                    break
                elif mtype == "error":
                    raise ProviderError(f"cartesia error: {msg.get('error')}")
        finally:
            send_task.cancel()
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass


# ── Persistent per-call WS (production) ────────────────────────────────────

class CartesiaPersistentWS:
    """Long-lived WebSocket that persists for the entire agent call.

    Connect once during pipeline.start() (while the greeting is being
    prepared) and reuse it for every LLM turn. This eliminates the
    300-500ms TCP+TLS handshake that CartesiaTTS pays on every response.

    Thread-safety note: asyncio is single-threaded; we never truly
    preempt. The reader task and synthesize() interleave only at `await`
    points, so per-context state is safe without locks.
    """

    def __init__(self, model: str | None = None, sample_rate: int | None = None):
        self._model = model or settings.cartesia_model
        self._sample_rate = sample_rate or settings.audio_sample_rate
        self._ws: object | None = None  # websockets.ClientConnection (v13+)
        self._reader_task: asyncio.Task | None = None
        # Only one synthesis active at a time (matches turn-taking model).
        self._active_ctx: str | None = None
        self._audio_q: asyncio.Queue | None = None

    async def connect(self) -> None:
        if not settings.cartesia_api_key:
            raise ProviderError("CARTESIA_API_KEY is not configured")
        try:
            self._ws = await websockets.connect(
                _ws_url(), max_size=None, ping_interval=5, ping_timeout=20
            )
            self._reader_task = asyncio.create_task(self._read_loop())
            log.info("cartesia.ws_connected")
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"cartesia persistent connect failed: {exc}") from exc

    async def _ensure_connected(self) -> None:
        """Reconnect if the WS was closed (e.g. server timeout between turns).

        websockets 13+ (ClientConnection) dropped .closed in favour of .state;
        older versions had .open / .closed on WebSocketClientProtocol.
        We probe both so this works across library versions.
        """
        if self._ws is not None and _ws_is_open(self._ws):
            return
        log.info("cartesia.ws_reconnecting")
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        await self.connect()

    async def _read_loop(self) -> None:
        """Pump all incoming Cartesia frames into the active synthesis queue."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                ctx_id = msg.get("context_id")
                # Route to the active synthesis queue; discard stale contexts
                # (e.g. from a barge-in-cancelled turn).
                if ctx_id == self._active_ctx:
                    q = self._audio_q
                    if q is not None:
                        await q.put(msg)
        except websockets.ConnectionClosed:
            log.warning("cartesia.ws_disconnected")
        except Exception as exc:  # noqa: BLE001
            log.warning("cartesia.read_error", error=str(exc))
        finally:
            # Unblock any synthesis awaiting a response.
            q = self._audio_q
            if q is not None:
                await q.put({"type": "error", "error": "cartesia ws closed"})

    async def synthesize(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
        language: str = "en",
    ) -> AsyncIterator[AudioChunk]:
        await self._ensure_connected()
        assert self._ws is not None

        context_id = uuid.uuid4().hex
        q: asyncio.Queue = asyncio.Queue()
        self._active_ctx = context_id
        self._audio_q = q

        def _payload(transcript: str, cont: bool) -> str:
            return json.dumps({
                "context_id": context_id,
                "model_id": self._model,
                "transcript": transcript,
                "voice": {"mode": "id", "id": voice_id},
                "language": language,
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": self._sample_rate,
                },
                "continue": cont,
            })

        async def _send() -> None:
            try:
                sent_any = False
                async for chunk in text_stream:
                    if not chunk:
                        continue
                    await self._ws.send(_payload(chunk, True))  # type: ignore[union-attr]
                    sent_any = True
                if sent_any:
                    # Normal path: flush to get remaining audio.
                    await self._ws.send(_payload("", False))  # type: ignore[union-attr]
                else:
                    # Tool-only LLM turn — no text to synthesize.
                    # Signal done directly; never touch Cartesia (empty transcript = 400).
                    await q.put({"type": "done"})
            except Exception as exc:  # noqa: BLE001
                await q.put({"type": "error", "error": str(exc)})

        send_task = asyncio.create_task(_send())
        try:
            while True:
                msg = await q.get()
                if not isinstance(msg, dict):
                    break
                mtype = msg.get("type")
                if mtype == "chunk" and msg.get("data"):
                    yield AudioChunk(
                        data=base64.b64decode(msg["data"]),
                        sample_rate=self._sample_rate,
                    )
                elif mtype == "done":
                    yield AudioChunk(data=b"", sample_rate=self._sample_rate, is_final=True)
                    break
                elif mtype == "error":
                    raise ProviderError(f"cartesia error: {msg.get('error')}")
        finally:
            send_task.cancel()
            # Guard: only clear if we are still the active synthesis.
            # If a newer turn started after a barge-in, _active_ctx has already
            # been overwritten — don't clobber it from this stale generator's GC.
            if self._active_ctx == context_id:
                self._active_ctx = None
                self._audio_q = None

    async def close(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
        log.info("cartesia.ws_closed")
