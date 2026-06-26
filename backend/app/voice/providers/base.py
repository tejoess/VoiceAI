"""Provider interfaces and shared streaming types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass
class Transcript:
    """A (possibly partial) STT result.

    ``is_final``     — this segment's text is finalized (user may keep talking).
    ``speech_final`` — Deepgram detected end-of-speech (endpointing). This is
                       the real "the caller finished their turn" signal.
    ``utterance_end``— backup end-of-turn marker from Deepgram's UtteranceEnd
                       event (fires when speech_final is missed). Carries no text.
    """

    text: str
    is_final: bool
    speech_final: bool = False
    utterance_end: bool = False
    language: str | None = None
    confidence: float | None = None


@dataclass
class LLMDelta:
    """A streamed chunk of LLM output."""

    text: str
    # Optional tool-call signal (name, arguments-json) when the model invokes a tool.
    tool_call: dict | None = None


@dataclass
class AudioChunk:
    """A chunk of synthesized PCM audio."""

    data: bytes
    sample_rate: int
    # True on the final chunk of an utterance.
    is_final: bool = False


class STTStream(Protocol):
    async def send_audio(self, frame: bytes) -> None: ...
    async def finalize(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[Transcript]: ...
    async def aclose(self) -> None: ...


class LLMClient(Protocol):
    def stream(
        self, messages: list[dict], **kwargs
    ) -> AsyncIterator[LLMDelta]: ...


class TTSClient(Protocol):
    def stream(
        self, text_stream: AsyncIterator[str], *, language: str, voice_id: str
    ) -> AsyncIterator[AudioChunk]: ...


class ProviderError(RuntimeError):
    """Raised when a provider call fails irrecoverably."""
