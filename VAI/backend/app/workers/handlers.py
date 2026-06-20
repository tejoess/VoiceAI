"""Concrete background task handlers.

These run off the realtime path. They are intentionally simple and idempotent
where possible. Real CRM/calendar integrations plug in here later.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger
from app.workers.tasks import register

log = get_logger(__name__)


@register("save_lead")
async def save_lead(payload: dict) -> None:
    lead = payload.get("lead", {})
    session = payload.get("session", {})
    # TODO: persist to a leads table / push to CRM. For now, log + webhook.
    log.info("lead.saved", agent=session.get("agent_id"), lead=lead)
    webhook = session.get("webhook_url")
    if webhook:
        await _post_webhook(webhook, {"type": "lead.captured", "lead": lead, "session": session})


@register("book_appointment")
async def book_appointment(payload: dict) -> None:
    appt = payload.get("appointment", {})
    session = payload.get("session", {})
    log.info("appointment.booked", agent=session.get("agent_id"), appointment=appt)
    webhook = session.get("webhook_url")
    if webhook:
        await _post_webhook(
            webhook, {"type": "appointment.booked", "appointment": appt, "session": session}
        )


@register("human_handoff")
async def human_handoff(payload: dict) -> None:
    session = payload.get("session", {})
    log.info("handoff.requested", agent=session.get("agent_id"), reason=payload.get("reason"))
    webhook = session.get("webhook_url")
    if webhook:
        await _post_webhook(
            webhook, {"type": "human.handoff", "reason": payload.get("reason"), "session": session}
        )


@register("webhook")
async def webhook(payload: dict) -> None:
    session = payload.get("session", {})
    url = session.get("webhook_url")
    if not url:
        log.info("webhook.skipped_no_url", agent=session.get("agent_id"))
        return
    await _post_webhook(
        url,
        {"type": payload.get("event", "custom"), "payload": payload.get("payload", {}), "session": session},
    )


@register("persist_session")
async def persist_session(payload: dict) -> None:
    """Write final transcript + metrics for a completed call."""
    from app.core.database import get_sessionmaker
    from app.models.session import CallSession
    import uuid as _uuid

    session_id = payload.get("session_id")
    if not session_id:
        return
    sm = get_sessionmaker()
    async with sm() as db:
        cs = await db.get(CallSession, _uuid.UUID(session_id))
        if cs is None:
            return
        cs.transcript = payload.get("transcript", cs.transcript)
        cs.metrics = payload.get("metrics", cs.metrics)
        cs.turn_count = payload.get("turn_count", cs.turn_count)
        cs.status = payload.get("status", "completed")
        cs.duration_seconds = payload.get("duration_seconds", cs.duration_seconds)
        await db.commit()
    log.info("session.persisted", session_id=session_id)


async def _post_webhook(url: str, body: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body)
            log.info("webhook.delivered", url=url, status=resp.status_code)
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook.delivery_failed", url=url, error=str(exc))
