"""Realtime voice pipeline: STT → LLM → TTS, fully streaming.

Latency techniques applied
--------------------------
1. LLM prompt caching
   System prompt is built ONCE at call start and reused every turn so
   OpenAI's automatic prefix cache gets a consistent hit (saves ~150ms/turn
   after the first turn).

2. Persistent Cartesia WebSocket per call
   pipeline.start() opens a single CartesiaPersistentWS alongside STT.
   Every LLM turn reuses that connection — zero WS-connect overhead.
   (Old prewarm saved ~150ms; this saves ~300-500ms EVERY TURN.)

3. Semantic end-of-turn prediction
   When Deepgram's is_final text ends with terminal punctuation (.?!।॥),
   we respond immediately without waiting for speech_final (~500ms) or the
   EOT timer (~600ms).  Cuts silence wait from ~550ms → ~0-50ms on most turns.

4. Fully decoupled streaming pipeline
   LLM tokens → text_q → TTS and LLM tokens → token_q → frontend run
   in two SEPARATE asyncio tasks so publish_data() latency never stalls
   the TTS path.

5. LLM output chunking (text_chunk.py)
   SentenceAggregator flushes at hard boundaries immediately and at soft
   boundaries after 14 chars (down from 24) so TTS gets text sooner.

6. Persistent TTS WebSocket (cartesia.py: CartesiaPersistentWS)
   One WS per call; _ensure_connected() auto-reconnects on drop.

7. max_tokens = 150
   Short, focused replies → less LLM generation time → less TTS time →
   faster turn-around. Agents should be brief on voice calls anyway.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from app.core.logging import get_logger
from app.data.languages import TTSProvider, get_language
from app.voice import router, tools
from app.voice.prompt_builder import AgentPromptConfig, build_system_prompt
from app.voice.providers.base import AudioChunk, Transcript
from app.voice.providers.cartesia import CartesiaPersistentWS
from app.voice.providers.deepgram import DeepgramSTT
from app.voice.providers.openai_llm import OpenAILLM
from app.voice.providers.text_chunk import SentenceAggregator

log = get_logger(__name__)

EmitAudio = Callable[[AudioChunk], Awaitable[None]]
EmitEvent = Callable[[str, dict], Awaitable[None]] | None

_BARGE_IN_MIN_CHARS = 3

# After the last is_final segment without speech_final, wait this long before
# responding anyway (Deepgram sometimes skips speech_final on noisy lines).
_EOT_SECS = 0.6

# Terminal punctuation set for semantic EOT prediction (#3).
# When is_final text ends with one of these we respond without waiting for
# speech_final or the EOT timer — cuts ~500ms of silence wait.
_EOT_PUNCT = frozenset(".?!।॥")

# Technique #7: keep LLM replies short on voice calls.
_DEFAULT_MAX_TOKENS = 150


def _looks_complete(text: str) -> bool:
    """Heuristic: does the finalized segment end at a natural sentence boundary?"""
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in _EOT_PUNCT


class VoicePipeline:
    def __init__(
        self,
        runtime_cfg: dict,
        *,
        emit_audio: EmitAudio,
        emit_event: EmitEvent = None,
        input_sample_rate: int = 48000,
    ):
        self.runtime_cfg = runtime_cfg
        self.cfg = AgentPromptConfig.from_dict(runtime_cfg)
        self.active_language = runtime_cfg.get("primary_language", "en")
        self.voice_id = runtime_cfg.get("voice_id")
        self.input_sample_rate = input_sample_rate

        self.history: list[dict] = []
        self._capabilities: list[str] = runtime_cfg.get("capabilities", [])
        self.session_ctx = {
            "agent_id": runtime_cfg.get("id"),
            "webhook_url": runtime_cfg.get("webhook_url"),
        }
        # Tool schemas are finalised in start() after checking whether the agent
        # has indexed knowledge docs (sets has_knowledge flag for search_kb tool).
        self.tool_schemas: list[dict] = []

        self._emit_audio = emit_audio
        self._emit_event = emit_event
        self._llm = OpenAILLM()
        self._stt_factory = DeepgramSTT()
        self._stt = None

        self._speaking = False
        self._gen_task: asyncio.Task | None = None
        self._closed = False
        self._gen_id: int = 0
        self._eot_timer: asyncio.TimerHandle | None = None
        self._pending_user = ""
        self.metrics = {"turns": 0, "first_audio_ms": [], "barge_ins": 0}

        # Technique #2/#6: persistent Cartesia WS (connected in start()).
        self._tts_ws: CartesiaPersistentWS | None = None

        # Optional callback invoked when the LLM calls end_call tool.
        # Set by agent_worker to disconnect the LiveKit room.
        self.on_end_call: Callable[[], Awaitable[None]] | None = None

        # Technique #1: build system prompt once, reuse every turn.
        # Identical content → OpenAI prefix cache hits every turn after the first.
        self._system_prompt: str = build_system_prompt(self.cfg, self.active_language)

    # ── lifecycle ──────────────────────────────────────────────
    async def start(self) -> None:
        lang = get_language(self.active_language) or {}
        dg_code = lang.get("deepgram_code", "en-IN")
        self._stt = self._stt_factory.stream(
            language=dg_code, sample_rate=self.input_sample_rate
        )

        # Technique #2/#6: open a persistent Cartesia WS for English calls.
        # Connect it in parallel with STT so both are ready before greet().
        # Every subsequent turn reuses the same WS — no per-turn TLS handshake.
        route = router.resolve_route(self.active_language, self.voice_id)
        agent_id = str(self.session_ctx.get("agent_id", ""))

        # Warm the RAG collection (pre-loads ChromaDB cache) in parallel with
        # the STT and TTS connections so there's zero cold-start on first search.
        async def _warm_rag():
            if not agent_id:
                return False
            try:
                from app.voice.providers.rag import count_chunks, warm_agent
                await warm_agent(agent_id)
                return (await count_chunks(agent_id)) > 0
            except Exception:  # noqa: BLE001
                return False

        if route.provider == TTSProvider.CARTESIA:
            self._tts_ws = CartesiaPersistentWS()
            results = await asyncio.gather(
                self._stt.start(), self._tts_ws.connect(), _warm_rag()
            )
            has_knowledge = results[2]
        else:
            self._tts_ws = None
            results = await asyncio.gather(self._stt.start(), _warm_rag())
            has_knowledge = results[1]

        # Finalise tool schema list now that we know if there are indexed docs.
        self.tool_schemas = tools.schemas_for_capabilities(
            self._capabilities, has_knowledge=has_knowledge
        )
        self._has_knowledge: bool = has_knowledge

        log.info(
            "pipeline.started",
            agent=agent_id,
            language=self.active_language,
            has_knowledge=has_knowledge,
            tools=[s["function"]["name"] for s in self.tool_schemas],
        )

    async def push_audio(self, frame: bytes) -> None:
        if self._stt is not None and not self._closed:
            await self._stt.send_audio(frame)

    async def aclose(self) -> None:
        self._closed = True
        self._cancel_eot_timer()
        await self._cancel_speech()
        if self._stt is not None:
            await self._stt.aclose()
        if self._tts_ws is not None:
            await self._tts_ws.close()
            self._tts_ws = None

    # ── greeting ───────────────────────────────────────────────
    async def greet(self) -> None:
        greeting = self.cfg.greeting.strip()
        if not greeting:
            return
        self.history.append({"role": "assistant", "content": greeting})
        await self._emit_transcript("assistant", greeting)
        await self._speak_text_stream(self._single(greeting))

    # ── STT consume loop ───────────────────────────────────────
    async def run(self) -> None:
        assert self._stt is not None
        async for tr in self._stt:  # type: Transcript
            if self._closed:
                break
            await self._on_transcript(tr)
        self._cancel_eot_timer()
        await self._maybe_respond()

    async def _on_transcript(self, tr: Transcript) -> None:
        if tr.utterance_end:
            log.info("pipeline.eot", source="utterance_end")
            self._cancel_eot_timer()
            await self._maybe_respond()
            return

        text = tr.text.strip()
        if not text:
            return

        log.info("stt.transcript", final=tr.is_final, speech_final=tr.speech_final, text=text)

        if not tr.is_final:
            await self._emit_event_safe("stt_partial", {"text": text})

        if self._speaking and len(text) >= _BARGE_IN_MIN_CHARS:
            self.metrics["barge_ins"] += 1
            log.info("pipeline.barge_in", text=text)
            await self._cancel_speech()

        if tr.is_final:
            self._pending_user = (self._pending_user + " " + text).strip()

            if tr.speech_final:
                # Fast path A: Deepgram's own endpointing confirmed end-of-turn.
                log.info("pipeline.eot", source="speech_final")
                self._cancel_eot_timer()
                await self._maybe_respond()

            elif _looks_complete(text):
                # Fast path B (technique #3): terminal punctuation → semantically
                # complete sentence.  Don't wait 500ms for Deepgram; respond now.
                log.info("pipeline.eot", source="semantic")
                self._cancel_eot_timer()
                await self._maybe_respond()

            else:
                # Fallback: arm the silence timer; if no further speech arrives
                # within _EOT_SECS we assume the turn is done.
                self._schedule_eot_timer()

    # ── EOT timer ──────────────────────────────────────────────
    def _schedule_eot_timer(self) -> None:
        self._cancel_eot_timer()
        loop = asyncio.get_event_loop()
        self._eot_timer = loop.call_later(
            _EOT_SECS,
            lambda: asyncio.ensure_future(self._eot_fire()),
        )

    def _cancel_eot_timer(self) -> None:
        if self._eot_timer is not None:
            self._eot_timer.cancel()
            self._eot_timer = None

    async def _eot_fire(self) -> None:
        self._eot_timer = None
        if self._pending_user.strip():
            log.info("pipeline.eot", source="timer", pending=self._pending_user.strip())
        await self._maybe_respond()

    # ── turn management ────────────────────────────────────────
    async def _maybe_respond(self) -> None:
        user_turn = self._pending_user.strip()
        if not user_turn:
            return
        self._pending_user = ""
        await self._cancel_speech()
        await self._emit_transcript("user", user_turn)
        self.history.append({"role": "user", "content": user_turn})
        self._gen_task = asyncio.create_task(self._generate(user_turn))

    async def _generate(self, user_text: str) -> None:
        my_gen_id = self._gen_id
        self._speaking = True
        self.metrics["turns"] += 1
        turn_started = time.monotonic()
        self._first_audio_at = None

        log.info("pipeline.generating", text=user_text[:80], turn=self.metrics["turns"])

        # Speculative RAG: launch the vector search NOW, in parallel with the
        # LLM's first pass. Embedding + ChromaDB query takes ~150 ms; LLM first
        # token takes 400-800 ms. By the time the LLM decides to call
        # search_knowledge_base, the result is already in the completed task.
        spec_rag_task: "asyncio.Task[str] | None" = None
        if self._has_knowledge:
            agent_id = str(self.session_ctx.get("agent_id", ""))
            if agent_id:
                from app.voice.providers.rag import search_agent_knowledge  # lazy
                spec_rag_task = asyncio.create_task(
                    search_agent_knowledge(agent_id, user_text, top_k=3)
                )

        try:
            # Technique #1: use cached system prompt instead of rebuilding it.
            messages: list[dict] = [
                {"role": "system", "content": self._system_prompt},
                *self.history[:-1],          # history minus the turn we just added
                {"role": "user", "content": user_text},
            ]

            spoken, tool_calls = await self._stream_completion(messages, turn_started, gen_id=my_gen_id)

            if tool_calls:
                await self._handle_tools(tool_calls, messages, spoken, gen_id=my_gen_id, spec_rag=spec_rag_task)
                spec_rag_task = None  # consumed by _handle_tools

            if spoken.strip():
                self.history.append({"role": "assistant", "content": spoken.strip()})
                await self._emit_transcript("assistant", spoken.strip())

            # LLM called end_call tool — fire callback after audio finishes.
            if self.session_ctx.get("_end_call_requested") and self.on_end_call:
                log.info("pipeline.end_call")
                asyncio.create_task(self.on_end_call())

            log.info(
                "pipeline.turn_done",
                turn=self.metrics["turns"],
                first_audio_ms=self.metrics["first_audio_ms"][-1] if self.metrics["first_audio_ms"] else None,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("pipeline.generate_error", error=str(exc), exc_info=True)
            await self._speak_fallback()
        finally:
            self._speaking = False
            # Cancel the speculative RAG task if the LLM never called the tool.
            if spec_rag_task is not None and not spec_rag_task.done():
                spec_rag_task.cancel()

    async def _stream_completion(
        self, messages: list[dict], turn_started: float, gen_id: int | None = None
    ) -> tuple[str, list[dict]]:
        """Stream one LLM turn → TTS.

        Technique #4: LLM tokens split into two parallel paths:
          text_q  → TTS (audio synthesis, latency-critical)
          token_q → frontend (display, not latency-critical)
        The two asyncio tasks run concurrently so a slow publish_data() call
        never stalls the TTS audio pipeline.
        """
        route = router.resolve_route(self.active_language, self.voice_id)
        # Use the persistent WS for Cartesia (no per-turn WS connect overhead).
        # Fall back to a fresh per-call instance for Sarvam / other providers.
        if self._tts_ws is not None and route.provider == TTSProvider.CARTESIA:
            tts_synth = self._tts_ws.synthesize
        else:
            tts_synth = router.tts_for(route.provider).synthesize

        text_q: asyncio.Queue[str | None] = asyncio.Queue()
        token_q: asyncio.Queue[str | None] = asyncio.Queue()
        collected: dict = {"text": "", "tools": []}

        # Fire-and-forget — publish_data round-trip (50-200ms) must NOT block
        # the critical path that leads to LLM→TTS→audio.
        asyncio.create_task(self._emit_event_safe("agent_turn_start", {}))

        async def produce() -> None:
            """Pull LLM deltas → split into TTS path and frontend path."""
            # Technique #5: SentenceAggregator (min_soft_len=4, first_chunk_max=25)
            # flushes "Sure," immediately and force-flushes after 25 chars max.
            agg = SentenceAggregator()
            try:
                async for delta in self._llm.stream(
                    messages,
                    temperature=self.runtime_cfg.get("llm_temperature", 0.7),
                    # Technique #7: cap at 150 tokens — concise voice replies.
                    max_tokens=self.runtime_cfg.get("max_tokens", _DEFAULT_MAX_TOKENS),
                    tools=self.tool_schemas or None,
                ):
                    if delta.tool_call:
                        collected["tools"].append(delta.tool_call)
                        continue
                    if delta.text:
                        collected["text"] += delta.text
                        # TTS path (latency-critical): send clause chunks.
                        for chunk in agg.push(delta.text):
                            await text_q.put(chunk)
                        # Frontend path (display only): put raw token in token_q.
                        # This is drained by emit_tokens() independently.
                        await token_q.put(delta.text)
                tail = agg.flush()
                if tail:
                    await text_q.put(tail)
            finally:
                await text_q.put(None)   # sentinel: TTS loop done
                await token_q.put(None)  # sentinel: token emitter done

        async def emit_tokens() -> None:
            """Drain token_q → publish_data (decoupled from TTS path)."""
            while True:
                token = await token_q.get()
                if token is None:
                    break
                await self._emit_event_safe("token", {"text": token})

        async def text_gen():
            while True:
                item = await text_q.get()
                if item is None:
                    break
                yield item

        producer = asyncio.create_task(produce())
        token_emitter = asyncio.create_task(emit_tokens())
        try:
            async for audio in tts_synth(
                text_gen(), voice_id=route.native_voice_id, language=route.language_tag
            ):
                if gen_id is not None and self._gen_id != gen_id:
                    log.info("pipeline.audio_dropped", reason="barge_in")
                    break
                if audio.data:
                    if getattr(self, "_first_audio_at", None) is None:
                        self._first_audio_at = time.monotonic()
                        self.metrics["first_audio_ms"].append(
                            round((self._first_audio_at - turn_started) * 1000)
                        )
                    await self._emit_audio(audio)
            await producer
            await token_emitter
        except asyncio.CancelledError:
            producer.cancel()
            token_emitter.cancel()
            raise
        return collected["text"], collected["tools"]

    async def _handle_tools(
        self,
        tool_calls: list[dict],
        messages: list[dict],
        spoken: str,
        gen_id: int | None = None,
        spec_rag: "asyncio.Task[str] | None" = None,
    ) -> None:
        import orjson

        tool_messages: list[dict] = []
        for tc in tool_calls:
            name = tc.get("name")
            handler = tools.get_handler(name)
            try:
                args = orjson.loads(tc.get("arguments") or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            if handler is None:
                continue

            t0 = time.monotonic()
            # For RAG: the speculative task started in parallel with the LLM's
            # first pass. It's almost always done by the time we reach here,
            # so awaiting it costs ~0 ms instead of a fresh 150 ms search.
            if name == "search_knowledge_base" and spec_rag is not None:
                try:
                    result = await spec_rag
                    log.info(
                        "tool.called",
                        name=name,
                        query=args.get("query", ""),
                        source="speculative",
                        wait_ms=round((time.monotonic() - t0) * 1000),
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("rag.speculative_failed", error=str(exc))
                    result = await handler(self.session_ctx, args)  # fallback
                finally:
                    spec_rag = None  # consume once; subsequent calls use handler
            else:
                result = await handler(self.session_ctx, args)
                log.info(
                    "tool.called",
                    name=name,
                    latency_ms=round((time.monotonic() - t0) * 1000),
                )

            tool_messages.append({"role": "assistant", "content": f"[called {name}]"})
            tool_messages.append({"role": "user", "content": f"[tool result: {result}] Continue naturally."})
            await self._emit_event_safe("tool_called", {"name": name, "args": args})

        # Only include the assistant's spoken text if there was any.
        # An empty assistant message can cause OpenAI to reject the request.
        prior = [{"role": "assistant", "content": spoken}] if spoken.strip() else []
        follow_messages = messages + prior + tool_messages
        more, _ = await self._stream_completion(follow_messages, time.monotonic(), gen_id=gen_id)
        if more:
            self.history.append({"role": "assistant", "content": more.strip()})

    async def _speak_fallback(self) -> None:
        fb = self.cfg.fallback_message.strip() or "Sorry, I had trouble with that. Could you say it again?"
        await self._speak_text_stream(self._single(fb))

    # ── helpers ────────────────────────────────────────────────
    async def _speak_text_stream(self, text_iter) -> None:
        route = router.resolve_route(self.active_language, self.voice_id)
        if self._tts_ws is not None and route.provider == TTSProvider.CARTESIA:
            synth = self._tts_ws.synthesize
        else:
            synth = router.tts_for(route.provider).synthesize
        async for audio in synth(
            text_iter, voice_id=route.native_voice_id, language=route.language_tag
        ):
            if audio.data:
                await self._emit_audio(audio)

    @staticmethod
    async def _single(text: str):
        yield text

    async def _cancel_speech(self) -> None:
        self._gen_id += 1
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            try:
                await self._gen_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._speaking = False

    async def _emit_transcript(self, role: str, text: str) -> None:
        await self._emit_event_safe("transcript", {"role": role, "text": text, "ts": time.time()})

    async def _emit_event_safe(self, name: str, data: dict) -> None:
        if self._emit_event is not None:
            try:
                await self._emit_event(name, data)
            except Exception:  # noqa: BLE001
                pass

    def switch_language(self, language: str) -> None:
        if get_language(language):
            self.active_language = language
            # Rebuild cached system prompt for the new language
            self._system_prompt = build_system_prompt(self.cfg, self.active_language)
