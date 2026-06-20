"""Deepgram streaming Speech-to-Text.

Opens a websocket per call stream, pushes raw PCM frames as they arrive from
the caller's mic, and yields partial + final transcripts. Interim results are
enabled so the pipeline can react to *partial* transcripts (barge-in, early
LLM warmup) without waiting for end-of-utterance.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from urllib.parse import urlencode

import websockets

from app.core.config import settings
from app.core.logging import get_logger
from app.voice.providers.base import ProviderError, Transcript

log = get_logger(__name__)

DEEPGRAM_WS = "wss://api.deepgram.com/v1/listen"


class DeepgramSTTStream:
    """A single live STT stream over a Deepgram websocket."""

    def __init__(
        self,
        *,
        language: str = "en-IN",
        sample_rate: int = 16000,
        model: str | None = None,
        endpointing_ms: int = 500,
    ):
        self._language = language
        self._sample_rate = sample_rate
        self._model = model or settings.deepgram_model
        self._endpointing_ms = endpointing_ms
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._queue: asyncio.Queue[Transcript | None] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        if not settings.deepgram_api_key:
            raise ProviderError("DEEPGRAM_API_KEY is not configured")

        params = {
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": str(self._sample_rate),
            "channels": "1",
            "interim_results": "true",
            "punctuate": "true",
            "smart_format": "true",
            # Wait ~500ms of silence before declaring end-of-speech, so brief
            # mid-sentence pauses don't end the caller's turn prematurely.
            "endpointing": str(self._endpointing_ms),
            # Backup end-of-turn signal if speech_final is missed (min 1000ms).
            "utterance_end_ms": "1000",
            "vad_events": "true",
        }
        # Deepgram uses "language"; "multi" enables code-switched recognition.
        if self._language:
            params["language"] = self._language

        url = f"{DEEPGRAM_WS}?{urlencode(params)}"
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
                ping_interval=5,
                ping_timeout=20,
                max_size=None,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"deepgram connect failed: {exc}") from exc

        self._reader_task = asyncio.create_task(self._read_loop())
        log.info("deepgram.stream_started", language=self._language, model=self._model)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue

                if not isinstance(msg, dict):
                    continue

                mtype = msg.get("type")

                # Backup end-of-turn event (no transcript payload).
                if mtype == "UtteranceEnd":
                    log.info("deepgram.utterance_end")
                    await self._queue.put(
                        Transcript(text="", is_final=False, utterance_end=True, language=self._language)
                    )
                    continue

                # Only "Results" messages carry a channel dict. vad_events also
                # emit SpeechStarted, where "channel" is a list of indices —
                # never index into those.
                if mtype != "Results":
                    continue

                channel = msg.get("channel")
                if not isinstance(channel, dict):
                    continue
                alternatives = channel.get("alternatives") or []
                if not alternatives:
                    continue
                alt = alternatives[0]
                text = (alt.get("transcript") or "").strip()
                if not text:
                    continue

                await self._queue.put(
                    Transcript(
                        text=text,
                        is_final=bool(msg.get("is_final")),
                        speech_final=bool(msg.get("speech_final")),
                        confidence=alt.get("confidence"),
                        language=self._language,
                    )
                )
        except websockets.ConnectionClosed:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("deepgram.read_loop_error", error=str(exc))
        finally:
            await self._queue.put(None)  # sentinel → end iteration

    async def send_audio(self, frame: bytes) -> None:
        if self._ws is None or self._closed:
            return
        try:
            await self._ws.send(frame)
        except websockets.ConnectionClosed:
            self._closed = True

    async def finalize(self) -> None:
        """Tell Deepgram to flush and close the stream cleanly."""
        if self._ws is None or self._closed:
            return
        try:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
        except websockets.ConnectionClosed:
            self._closed = True

    def __aiter__(self) -> AsyncIterator[Transcript]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[Transcript]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    async def aclose(self) -> None:
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None


class DeepgramSTT:
    """Factory for per-call STT streams (warmed at startup)."""

    def stream(
        self,
        *,
        language: str = "en-IN",
        sample_rate: int = 16000,
        endpointing_ms: int = 500,
    ) -> DeepgramSTTStream:
        return DeepgramSTTStream(
            language=language, sample_rate=sample_rate, endpointing_ms=endpointing_ms
        )
