"""Tool registry for agent capabilities.

Each tool exposes an OpenAI function schema (for the LLM) and an async handler
(executed when the model calls it). Handlers must be fast and non-blocking on
the realtime path — anything heavy is handed to a background worker.

Built-in tools (always sent to the LLM regardless of capabilities):
  - end_call   : LLM signals goodbye and ends the session gracefully.
  - search_knowledge_base : RAG retrieval (only when agent has knowledge docs).

Capability-gated tools (only sent when the agent enables the capability):
  - save_lead, book_appointment, request_human_handoff, trigger_webhook
"""

from __future__ import annotations

from typing import Awaitable, Callable

from app.core.logging import get_logger
from app.data.capabilities import tools_for_capabilities
from app.workers import tasks as bg

log = get_logger(__name__)

Handler = Callable[[dict, dict], Awaitable[str]]


# ── Built-in handlers ──────────────────────────────────────────────────────

async def _end_call(ctx: dict, args: dict) -> str:
    """Signal the pipeline to end the call after this response finishes."""
    ctx["_end_call_requested"] = True
    farewell = args.get("farewell", "")
    return farewell or "Goodbye! Have a great day."


async def _search_knowledge_base(ctx: dict, args: dict) -> str:
    """Async RAG retrieval from the agent's uploaded knowledge documents."""
    agent_id = ctx.get("agent_id")
    query = args.get("query", "").strip()
    if not agent_id or not query:
        return "No relevant information found."
    try:
        from app.voice.providers.rag import search_agent_knowledge  # lazy import
        return await search_agent_knowledge(str(agent_id), query, top_k=3)
    except Exception as exc:  # noqa: BLE001
        log.warning("rag.search_failed", error=str(exc))
        return "Could not retrieve information right now."


# ── Capability-gated handlers ──────────────────────────────────────────────

async def _save_lead(ctx: dict, args: dict) -> str:
    await bg.enqueue("save_lead", {"session": ctx, "lead": args})
    return "Lead captured."


async def _book_appointment(ctx: dict, args: dict) -> str:
    await bg.enqueue("book_appointment", {"session": ctx, "appointment": args})
    when = args.get("datetime") or args.get("date") or "the requested time"
    return f"Appointment request recorded for {when}."


async def _request_human_handoff(ctx: dict, args: dict) -> str:
    await bg.enqueue("human_handoff", {"session": ctx, "reason": args.get("reason")})
    return "Human handoff requested. A person will join shortly."


async def _trigger_webhook(ctx: dict, args: dict) -> str:
    await bg.enqueue(
        "webhook",
        {"session": ctx, "event": args.get("event", "custom"), "payload": args},
    )
    return "Event sent."


# ── Schemas ────────────────────────────────────────────────────────────────

_BUILTIN_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": (
                "End the phone call gracefully. Call this when the user says "
                "goodbye, thank you and bye, I'm done, or any clear farewell. "
                "Say your goodbye line first, then call this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "farewell": {
                        "type": "string",
                        "description": "Optional spoken farewell already said.",
                    }
                },
            },
        },
    },
]

_RAG_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "Search uploaded documents for specific information about this business "
            "(hours, menu, pricing, services, policies, etc.). "
            "Call this tool whenever the caller asks something that may be answered "
            "by the business's documents. Do NOT guess or make up facts — always "
            "look them up first, then answer naturally as if you know."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise search query capturing the caller's question.",
                }
            },
            "required": ["query"],
        },
    },
}

_CAPABILITY_SCHEMAS: dict[str, dict] = {
    "save_lead": {
        "type": "function",
        "function": {
            "name": "save_lead",
            "description": "Save a captured lead (caller contact + intent).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "reason": {"type": "string", "description": "Why they called."},
                },
                "required": ["name"],
            },
        },
    },
    "book_appointment": {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Record an appointment booking request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "service": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "datetime": {"type": "string", "description": "ISO datetime if known."},
                    "notes": {"type": "string"},
                },
                "required": ["date", "time"],
            },
        },
    },
    "request_human_handoff": {
        "type": "function",
        "function": {
            "name": "request_human_handoff",
            "description": "Escalate the call to a human agent.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
            },
        },
    },
    "trigger_webhook": {
        "type": "function",
        "function": {
            "name": "trigger_webhook",
            "description": "Send a custom event to the business's configured webhook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["event"],
            },
        },
    },
}

_HANDLERS: dict[str, Handler] = {
    "end_call": _end_call,
    "search_knowledge_base": _search_knowledge_base,
    "save_lead": _save_lead,
    "book_appointment": _book_appointment,
    "request_human_handoff": _request_human_handoff,
    "trigger_webhook": _trigger_webhook,
}


def schemas_for_capabilities(
    capabilities: list[str],
    *,
    has_knowledge: bool = False,
) -> list[dict]:
    """Build the tool schema list sent to the LLM.

    Always includes end_call. Adds search_knowledge_base when the agent has
    uploaded knowledge docs. Adds capability-gated tools based on the agent's
    enabled capabilities.
    """
    schemas = list(_BUILTIN_SCHEMAS)

    if has_knowledge:
        schemas.append(_RAG_SCHEMA)

    names = tools_for_capabilities(capabilities)
    schemas.extend(_CAPABILITY_SCHEMAS[n] for n in names if n in _CAPABILITY_SCHEMAS)
    return schemas


def get_handler(name: str) -> Handler | None:
    return _HANDLERS.get(name)
