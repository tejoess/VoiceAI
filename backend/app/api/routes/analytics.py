"""Lightweight analytics rollups for the dashboard."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.agent import Agent
from app.models.session import CallSession

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db), agent_id: uuid.UUID | None = None
) -> dict:
    base = select(CallSession)
    if agent_id:
        base = base.where(CallSession.agent_id == agent_id)

    total_sessions = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    agent_count = (await db.execute(select(func.count()).select_from(Agent))).scalar_one()

    dur_stmt = select(func.coalesce(func.avg(CallSession.duration_seconds), 0.0))
    turns_stmt = select(func.coalesce(func.avg(CallSession.turn_count), 0.0))
    if agent_id:
        dur_stmt = dur_stmt.where(CallSession.agent_id == agent_id)
        turns_stmt = turns_stmt.where(CallSession.agent_id == agent_id)

    avg_duration = (await db.execute(dur_stmt)).scalar_one()
    avg_turns = (await db.execute(turns_stmt)).scalar_one()

    # Sessions per language.
    lang_stmt = select(CallSession.language, func.count()).group_by(CallSession.language)
    if agent_id:
        lang_stmt = lang_stmt.where(CallSession.agent_id == agent_id)
    by_language = {lang: count for lang, count in (await db.execute(lang_stmt)).all()}

    return {
        "agents": agent_count,
        "total_sessions": total_sessions,
        "avg_duration_seconds": round(float(avg_duration), 1),
        "avg_turns": round(float(avg_turns), 1),
        "sessions_by_language": by_language,
    }
