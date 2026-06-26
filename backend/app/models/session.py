"""Call session model — one browser/telephony voice session with an agent.

Persisted for analytics and transcript review. The realtime worker writes the
final transcript and latency metrics here via a background task so it never
blocks the audio path.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class CallSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "call_sessions"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # LiveKit room this session ran in.
    room_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(30), default="web", nullable=False)  # web | phone
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)  # active|completed|failed
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Conversation transcript: list of {role, text, ts}.
    transcript: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Latency / quality metrics: e.g. avg_first_token_ms, avg_tts_ms, turns.
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    agent: Mapped["Agent"] = relationship(back_populates="sessions")  # noqa: F821
