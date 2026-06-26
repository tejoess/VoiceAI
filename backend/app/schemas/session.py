"""Session + voice-testing schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConnectRequest(BaseModel):
    """Request a LiveKit access token to test an agent from the browser."""

    agent_id: uuid.UUID
    # Optional override of the language to test (must be in the agent's set).
    language: str | None = None
    # Display name for the participant (browser tester).
    participant_name: str = Field("tester", max_length=100)


class ConnectResponse(BaseModel):
    token: str
    url: str
    room_name: str
    agent_id: uuid.UUID
    livekit_configured: bool


class TranscriptTurn(BaseModel):
    role: str  # "user" | "assistant"
    text: str
    ts: float


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    room_name: str
    channel: str
    status: str
    language: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    transcript: list
    metrics: dict
    turn_count: int
    created_at: datetime
