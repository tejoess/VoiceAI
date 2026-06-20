"""Agent CRUD + cached realtime config loading.

The REST API uses the CRUD functions; the realtime worker uses
``get_runtime_config`` which returns a cached, JSON-safe projection of the
agent (plus its business context) so building a prompt mid-call never touches
the database.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import agent_key, cache
from app.core.logging import get_logger
from app.models.agent import Agent
from app.models.business import Business
from app.schemas.agent import AgentCreate, AgentUpdate

log = get_logger(__name__)


# ── CRUD ───────────────────────────────────────────────────────
async def create_agent(db: AsyncSession, data: AgentCreate) -> Agent:
    agent = Agent(**data.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    return await db.get(Agent, agent_id)


async def list_agents(db: AsyncSession, limit: int = 100, offset: int = 0) -> list[Agent]:
    result = await db.execute(
        select(Agent).order_by(Agent.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def update_agent(
    db: AsyncSession, agent_id: uuid.UUID, data: AgentUpdate
) -> Agent | None:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    # primary_language must remain in languages
    if agent.primary_language not in agent.languages:
        agent.languages = [agent.primary_language, *agent.languages]
    await db.flush()
    await db.refresh(agent)
    await invalidate_runtime_config(str(agent_id))
    return agent


async def delete_agent(db: AsyncSession, agent_id: uuid.UUID) -> bool:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        return False
    await db.delete(agent)
    await invalidate_runtime_config(str(agent_id))
    return True


# ── Realtime cached config ─────────────────────────────────────
def _to_runtime_dict(agent: Agent, business: Business | None) -> dict:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "system_prompt": agent.system_prompt,
        "greeting": agent.greeting,
        "fallback_message": agent.fallback_message,
        "voice_id": agent.voice_id,
        "primary_language": agent.primary_language,
        "languages": list(agent.languages or []),
        "tone": agent.tone,
        "speaking_style": agent.speaking_style,
        "capabilities": list(agent.capabilities or []),
        "llm_temperature": agent.llm_temperature,
        "max_tokens": agent.max_tokens,
        "webhook_url": agent.webhook_url,
        "business_name": business.name if business else None,
        "business_context": business.context if business else None,
    }


async def get_runtime_config(db: AsyncSession, agent_id: uuid.UUID) -> dict | None:
    """Cached agent projection for the realtime path."""
    key = agent_key(str(agent_id))
    cached = await cache.get(key)
    if cached is not None:
        return cached

    agent = await db.get(Agent, agent_id)
    if agent is None:
        return None
    business = await db.get(Business, agent.business_id) if agent.business_id else None
    data = _to_runtime_dict(agent, business)
    await cache.set(key, data)
    return data


async def invalidate_runtime_config(agent_id: str) -> None:
    await cache.invalidate(agent_key(agent_id))
