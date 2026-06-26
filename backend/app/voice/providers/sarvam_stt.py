"""Sarvam AI Speech-to-Text (Saarika v2).

Uses Sarvam's batch REST API with energy-based voice-activity detection (VAD)
to simulate the same transcript stream interface as DeepgramSTT.

Architecture
-----------
* Raw PCM frames arrive via send_audio().
* A lightweight energy VAD groups frames into utterances:
  - Speech starts when RMS > SPEECH_THRESH for 3+ consecutive frames.
  - Speech ends when RMS < SILENCE_THRESH for SILENCE_FRAMES consecutive frames
    (default 25 × 20ms = 500ms of silence).
* Each complete utterance is sent to POST /speech-to-text in a background task.
* Results are published as final Transcripts on the async queue.
* An UtteranceEnd sentinel is injected right after the REST response so the
  pipeline's EOT logic fires identically to Deepgram mode.

Caveats
-------
* No interim/partial results (Sarvam REST is batch).  The pipeline won't get
  barge-in signals mid-utterance; it will only react at utterance boundaries.
* Latency = utterance_audio_duration + REST round-trip (~200-600ms).
"""

from __future__ import annotations

import asyncio
import io
import struct
import wave
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.voice.providers.base import ProviderError, Transcript

log = get_logger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

# VAD tuning
_FRAME_MS = 20                # process audio in 20ms frames
_SPEECH_THRESH = 150          # RMS level considered speech
_SILENCE_THRESH = 100         # RMS level considered silence
_SPEECH_ONSET_FRAMES = 3      # frames above threshold to start utterance
_SILENCE_FRAMES_EOT = 25      # frames below threshold to end utterance (500ms)
_MAX_UTTERANCE_SECS = 30      # hard limit on utterance length


def _rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack_from(f"<{n}h", pcm)
    return (sum(s * s for s in samples) / n) ** 0.5


_TARGET_SR = 16000  # Sarvam batch API supports 8000 / 16000 Hz


def _downsample(pcm: bytes, src_rate: int, dst_rate: int = _TARGET_SR) -> bytes:
    """Simple integer decimation (average N samples → 1). Good enough for speech."""
    if src_rate == dst_rate:
        return pcm
    ratio = src_rate // dst_rate
    if ratio < 1:
        return pcm
    n_src = len(pcm) // 2
    out = bytearray()
    for i in range(0, n_src - ratio + 1, ratio):
        acc = 0
        for j in range(ratio):
            acc += struct.unpack_from("<h", pcm, (i + j) * 2)[0]
        avg = max(-32768, min(32767, acc // ratio))
        out += struct.pack("<h", avg)
    return bytes(out)


class SarvamSTTStream:
    """A single live STT stream backed by Sarvam batch API + energy VAD."""

    def __init__(
        self,
        *,
        language: str = "hi-IN",
        sample_rate: int = 16000,
    ):
        self._language = language
        self._sample_rate = sample_rate
        self._target_rate = _TARGET_SR
        # Frame size at the incoming sample rate (for VAD)
        self._frame_bytes = (sample_rate * _FRAME_MS // 1000) * 2  # 16-bit PCM

        self._queue: asyncio.Queue[Transcript | None] = asyncio.Queue()
        self._audio_buf = bytearray()          # raw incoming PCM
        self._utterance_buf = bytearray()      # current speech segment
        self._speech_frames = 0
        self._silence_frames = 0
        self._in_speech = False
        self._closed = False
        self._pending: asyncio.Queue[bytes] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        if not settings.sarvam_api_key:
            raise ProviderError("SARVAM_API_KEY is not configured")
        self._worker_task = asyncio.create_task(self._transcribe_loop())
        log.info("sarvam_stt.stream_started", language=self._language)

    async def send_audio(self, frame: bytes) -> None:
        if self._closed:
            return
        self._audio_buf.extend(frame)
        # Process in 20ms frames
        while len(self._audio_buf) >= self._frame_bytes:
            chunk = bytes(self._audio_buf[: self._frame_bytes])
            self._audio_buf = self._audio_buf[self._frame_bytes :]
            self._process_frame(chunk)

    def _process_frame(self, frame: bytes) -> None:
        energy = _rms(frame)

        if energy > _SPEECH_THRESH:
            self._silence_frames = 0
            if not self._in_speech:
                self._speech_frames += 1
                if self._speech_frames >= _SPEECH_ONSET_FRAMES:
                    self._in_speech = True
                    self._speech_frames = 0
            if self._in_speech:
                self._utterance_buf.extend(frame)
        else:
            self._speech_frames = 0
            if self._in_speech:
                self._utterance_buf.extend(frame)
                self._silence_frames += 1
                if self._silence_frames >= _SILENCE_FRAMES_EOT:
                    self._flush_utterance()
            else:
                self._silence_frames = 0

        # Hard cap to avoid very long utterances
        max_bytes = _MAX_UTTERANCE_SECS * self._sample_rate * 2
        if self._in_speech and len(self._utterance_buf) > max_bytes:
            self._flush_utterance()

    def _flush_utterance(self) -> None:
        if len(self._utterance_buf) < self._frame_bytes * 2:
            self._utterance_buf.clear()
            self._in_speech = False
            self._silence_frames = 0
            return
        audio = bytes(self._utterance_buf)
        self._utterance_buf = bytearray()
        self._in_speech = False
        self._silence_frames = 0
        self._pending.put_nowait(audio)

    async def _transcribe_loop(self) -> None:
        while not self._closed:
            try:
                pcm = await asyncio.wait_for(self._pending.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            try:
                text = await self._call_api(pcm)
                if text:
                    await self._queue.put(
                        Transcript(
                            text=text,
                            is_final=True,
                            speech_final=True,
                            language=self._language,
                        )
                    )
                    # Inject utterance_end so the pipeline EOT fires
                    await self._queue.put(
                        Transcript(
                            text="",
                            is_final=False,
                            utterance_end=True,
                            language=self._language,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("sarvam_stt.transcribe_error", error=str(exc))
        await self._queue.put(None)

    async def _call_api(self, pcm: bytes) -> str:
        audio = _downsample(pcm, self._sample_rate, self._target_rate)
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._target_rate)
            wf.writeframes(audio)
        wav_buf.seek(0)

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(
                SARVAM_STT_URL,
                files={"file": ("audio.wav", wav_buf, "audio/wav")},
                data={"model": "saarika:v2.5", "language_code": self._language},
                headers={"api-subscription-key": settings.sarvam_api_key},
            )
            if not resp.is_success:
                log.warning("sarvam_stt.api_error", status=resp.status_code, body=resp.text[:200])
                return ""
            return resp.json().get("transcript", "").strip()

    def __aiter__(self) -> AsyncIterator[Transcript]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[Transcript]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    async def finalize(self) -> None:
        # Flush any in-progress utterance
        if self._in_speech and len(self._utterance_buf) > self._frame_bytes:
            self._flush_utterance()

    async def aclose(self) -> None:
        self._closed = True
        if self._worker_task:
            self._worker_task.cancel()


class SarvamSTT:
    """Factory for per-call Sarvam STT streams (Saarika v2 batch API)."""

    def stream(
        self,
        *,
        language: str = "hi-IN",
        sample_rate: int = 16000,
        **_kwargs,
    ) -> SarvamSTTStream:
        return SarvamSTTStream(language=language, sample_rate=sample_rate)

    # Conform to the same interface as DeepgramSTT for duck-typing.
    provider_name = "sarvam"
