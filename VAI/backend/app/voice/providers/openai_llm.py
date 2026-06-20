"""OpenAI streaming LLM client.

A single ``AsyncOpenAI`` client is created at startup and reused (it keeps an
HTTP/2 connection pool warm). ``stream`` yields token deltas the instant they
arrive so the pipeline can forward partial text to TTS without waiting for the
full response.
"""

from __future__ import annotations

from typing import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.voice.providers.base import LLMDelta, ProviderError

log = get_logger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not configured")
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            max_retries=2,
            timeout=30.0,
        )
    return _client


async def warmup() -> bool:
    """Cheaply validate credentials so the first real call isn't the first
    network round-trip. Returns False if not configured (non-fatal)."""
    if not settings.openai_api_key:
        return False
    try:
        client = get_client()
        await client.models.list()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("openai.warmup_failed", error=str(exc))
        return False


class OpenAILLM:
    def __init__(self, model: str | None = None):
        self._model = model or settings.openai_model

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 300,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[LLMDelta]:
        client = get_client()
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"openai stream failed: {exc}") from exc

        # Accumulate tool-call fragments across deltas.
        tool_acc: dict[int, dict] = {}

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                yield LLMDelta(text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tool_acc.setdefault(tc.index, {"name": "", "arguments": ""})
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments

            finish = chunk.choices[0].finish_reason
            if finish == "tool_calls":
                for slot in tool_acc.values():
                    yield LLMDelta(text="", tool_call=slot)
                tool_acc.clear()
