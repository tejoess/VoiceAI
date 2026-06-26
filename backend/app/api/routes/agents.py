"""Agent CRUD + prompt preview."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.services import agent_service
from app.voice.prompt_builder import AgentPromptConfig, build_system_prompt

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)) -> AgentRead:
    agent = await agent_service.create_agent(db, data)
    return AgentRead.model_validate(agent)


@router.get("", response_model=list[AgentRead])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
) -> list[AgentRead]:
    agents = await agent_service.list_agents(db, limit=limit, offset=offset)
    return [AgentRead.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AgentRead:
    agent = await agent_service.get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return AgentRead.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: uuid.UUID, data: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> AgentRead:
    agent = await agent_service.update_agent(db, agent_id, data)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return AgentRead.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    ok = await agent_service.delete_agent(db, agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="agent not found")
    return None


@router.get("/{agent_id}/prompt-preview")
async def prompt_preview(
    agent_id: uuid.UUID,
    language: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Render the fully-assembled system prompt for inspection in the UI."""
    cfg = await agent_service.get_runtime_config(db, agent_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="agent not found")
    prompt_cfg = AgentPromptConfig.from_dict(cfg)
    active = language or cfg["primary_language"]
    return {
        "agent_id": str(agent_id),
        "active_language": active,
        "system_prompt": build_system_prompt(prompt_cfg, active_language=active),
    }
