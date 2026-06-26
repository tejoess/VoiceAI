"""Voice-testing session endpoints: mint a LiveKit token + list past sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.session import CallSession
from app.schemas.session import ConnectRequest, ConnectResponse, SessionRead
from app.services import agent_service, livekit_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/connect", response_model=ConnectResponse)
async def connect(req: ConnectRequest, db: AsyncSession = Depends(get_db)) -> ConnectResponse:
    """Create a room + token for browser voice testing of an agent."""
    cfg = await agent_service.get_runtime_config(db, req.agent_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="agent not found")

    if req.language and req.language not in cfg["languages"]:
        raise HTTPException(status_code=400, detail="language not enabled for this agent")

    livekit_ready = all(
        [settings.livekit_api_key, settings.livekit_api_secret, settings.livekit_url]
    )

    room_name = livekit_service.make_room_name(req.agent_id)

    # Record the session up front (status active); the worker fills in
    # transcript/metrics via a background task at end-of-call.
    session = CallSession(
        agent_id=req.agent_id,
        room_name=room_name,
        channel="web",
        status="active",
        language=req.language or cfg["primary_language"],
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()

    token = ""
    if livekit_ready:
        token = livekit_service.create_access_token(
            room_name=room_name,
            identity=f"tester_{uuid.uuid4().hex[:8]}",
            name=req.participant_name,
        )

    return ConnectResponse(
        token=token,
        url=settings.livekit_url,
        room_name=room_name,
        agent_id=req.agent_id,
        livekit_configured=livekit_ready,
    )


@router.get("", response_model=list[SessionRead])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    agent_id: uuid.UUID | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> list[SessionRead]:
    stmt = select(CallSession).order_by(CallSession.created_at.desc())
    if agent_id:
        stmt = stmt.where(CallSession.agent_id == agent_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [SessionRead.model_validate(r) for r in rows]


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> SessionRead:
    row = await db.get(CallSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionRead.model_validate(row)
