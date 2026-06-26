# Voice AI Agent Platform

A production-grade, **multilingual (Indian-first) voice AI agent platform** — think
Ringg AI / Vapi, focused on Indian languages. Build configurable AI voice agents and
test them live in the browser over **WebRTC**. Telephony (Twilio / Exotel / Vobiz /
SIP) is intentionally **not** built yet — the foundation is modular so it slots in
later without rework.

```
Browser (Next.js)  ──WebRTC──►  LiveKit  ──►  Agent Worker (Python)
                                                  │
                    Deepgram STT  ◄── audio ──┐   │  streaming pipeline
                    OpenAI GPT-4.1 (LLM)      ├───┤  STT → LLM → TTS
                    Cartesia / Sarvam TTS  ───┘   │  (never waits for full sentences)
                                                  ▼
                                      Postgres + Redis (config, cache, queue)
```

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router), React, TypeScript, Tailwind, shadcn-style UI |
| Backend | Python 3.12, FastAPI, SQLAlchemy (async) |
| Database | PostgreSQL | 
| Cache / Queue | Redis |
| Realtime transport | LiveKit (WebRTC) |
| STT | Deepgram (streaming, interim results) |
| LLM | OpenAI GPT-4.1 (streaming) |
| TTS — English | Cartesia (`sonic-2`, websocket streaming) |
| TTS — Indian languages | Sarvam AI (`bulbul:v2`, per-clause streaming) |

**Voice routing:** English → Cartesia, all Indian languages → Sarvam AI. Enforced
centrally in [`backend/app/voice/router.py`](backend/app/voice/router.py).

**Languages:** English, Hindi, Hinglish, Marathi, Gujarati, Tamil, Telugu, Kannada,
Malayalam, Bengali.

---

## Repository layout

```
VAI/
├── backend/
│   └── app/
│       ├── main.py                # FastAPI app + lifespan warmup
│       ├── core/                  # config, db pool, redis pool, 2-tier cache, logging
│       ├── data/                  # static catalogs: languages, voices, tones, styles, capabilities
│       ├── models/                # SQLAlchemy models (Business, Agent, CallSession)
│       ├── schemas/               # Pydantic schemas (registry-validated)
│       ├── services/              # registry, agent CRUD + cached runtime config, LiveKit tokens
│       ├── api/routes/            # health, catalog, agents, sessions, analytics
│       ├── voice/
│       │   ├── templates.py       # preloaded Global prompt
│       │   ├── prompt_builder.py  # LAYERED prompt construction
│       │   ├── providers/         # Deepgram / OpenAI / Cartesia / Sarvam streaming clients
│       │   ├── router.py          # language → TTS provider routing
│       │   ├── tools.py           # capability → tool schemas + handlers
│       │   ├── pipeline.py        # STT→LLM→TTS streaming orchestrator + barge-in
│       │   └── agent_worker.py    # LiveKit worker entrypoint
│       ├── workers/               # Redis-backed background tasks (webhooks, leads, persistence)
│       └── scripts/seed.py        # sample business + agents
└── frontend/
    ├── app/                       # dashboard, agents (list/new/edit/test), analytics, settings
    ├── components/                # sidebar, agent-form, voice-tester, ui/* (shadcn-style)
    └── lib/                       # api client, types
```

---

## Prompt construction (layered)

The system prompt is assembled fresh each turn from ordered layers
([`prompt_builder.py`](backend/app/voice/prompt_builder.py)):

1. **Global** — voice-channel rules (no markdown, short turns, spoken numbers, ASR-error tolerance)
2. **Business** — company name + context
3. **Agent** — the agent's own system prompt
4. **Tone** — attitude preset
5. **Language** — which language to speak + how (+ code-switch allowance)
6. **Capabilities** — enabled features and behavior
7. **Greeting / Fallback** — kept consistent
8. **Future RAG context** — injected when retrieval lands

Conversation history + current user input are appended as separate chat messages so
the system prompt stays stable/cacheable across turns. Preview the rendered prompt per
agent at **Agents → (agent) → Prompt preview**, or `GET /api/v1/agents/{id}/prompt-preview`.

---

## Latency design

- **Warm on startup:** DB pool, Redis pool, preloaded prompt templates, preloaded
  language/voice/tone/style/capability catalogs, OpenAI credential check
  ([`main.py`](backend/app/main.py) lifespan).
- **Persistent connections & pools:** single async SQLAlchemy engine, Redis pool,
  reused OpenAI/HTTP clients.
- **Two-tier cache** ([`core/cache.py`](backend/app/core/cache.py)): in-process dict
  (zero network hop on the realtime path) over Redis. Agent configs cached and
  invalidated on update; static catalogs pinned in-process.
- **Everything streams:** Deepgram interim transcripts → GPT-4.1 token deltas →
  clause-chunked TTS → audio emitted immediately. **Barge-in** cancels in-flight
  LLM+TTS the moment the caller starts speaking.
- **Background workers** handle all non-realtime work (webhooks, lead/appointment
  persistence, transcript storage) off the audio path.

---

## Getting started

### Prerequisites
- Python 3.12, Node 18+, PostgreSQL, Redis.

### 1) Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # then fill in keys (see below)

# Postgres must be reachable per DATABASE_URL. Create the DB once:
#   createdb vai
python -m app.scripts.seed                           # optional: sample agents
uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs · health at `/api/v1/health`.

### 2) Realtime agent worker (needs LiveKit + provider keys)

```bash
cd backend
python -m app.voice.agent_worker dev
```

### 3) Background worker

```bash
cd backend
python -m app.workers.worker
```

### 4) Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev          # http://localhost:3000  (proxies /api/* to :8000)
```

---

## API keys

The platform **boots without any keys** — `/health` reports what's configured and the
UI shows provider status. Add keys to `backend/.env` as you get them:

| Key | Needed for | Notes |
|---|---|---|
| `OPENAI_API_KEY` | LLM responses | Required for any actual conversation. |
| `DEEPGRAM_API_KEY` | Speech-to-text | Free tier works for testing. |
| `CARTESIA_API_KEY` | English TTS | |
| `SARVAM_API_KEY` | Indian-language TTS | |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | Browser WebRTC + worker dispatch | Without these, the UI still works; the "Start call" button reports LiveKit isn't configured. |

You can configure agents, preview prompts, and browse the whole UI with **zero keys**.
Live audio needs LiveKit + Deepgram + OpenAI + (Cartesia or Sarvam) for the language
under test.

---

## What's stubbed for the future (by design)

These have clear seams and are surfaced in the UI as "coming soon" where relevant:

- **RAG / document upload** — prompt layer + capability already wired; retrieval not implemented.
- **Telephony** — Twilio / Exotel / Vobiz / SIP. The `CallSession.channel` field and
  worker dispatch are channel-agnostic.
- **Tool marketplace** — add tools in [`voice/tools.py`](backend/app/voice/tools.py),
  gate behind a capability.
- **CRM integration** — capability + webhook handler stub in
  [`workers/handlers.py`](backend/app/workers/handlers.py).

---

## Notes on the realtime worker

The LiveKit worker uses the Agents framework for **worker lifecycle + job dispatch**
only, then does raw `livekit.rtc` audio I/O so the streaming pipeline keeps full
control over partial transcripts and barge-in. The same provider clients power both
the worker and direct smoke tests. This path requires a LiveKit project; it can't be
exercised without one, so it's written to be reviewed and run once credentials exist.
