"""Agent model — the configurable voice agent."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Agent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agents"

    business_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Identity ───────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Prompt configuration ───────────────────────────────────
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    greeting: Mapped[str] = mapped_column(Text, default="", nullable=False)
    fallback_message: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # ── Voice / language / style (ids into the static registry) ─
    voice_id: Mapped[str] = mapped_column(String(100), default="cartesia_isha", nullable=False)
    primary_language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    languages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    tone: Mapped[str] = mapped_column(String(50), default="friendly", nullable=False)
    speaking_style: Mapped[str] = mapped_column(String(50), default="conversational", nullable=False)
    capabilities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    stt_provider: Mapped[str] = mapped_column(String(20), default="deepgram", nullable=False)

    # ── LLM tuning ─────────────────────────────────────────────
    llm_temperature: Mapped[float] = mapped_column(default=0.7, nullable=False)
    max_tokens: Mapped[int] = mapped_column(default=300, nullable=False)

    # ── Extensibility: webhook + arbitrary settings ────────────
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    business: Mapped["Business | None"] = relationship(back_populates="agents")  # noqa: F821
    sessions: Mapped[list["CallSession"]] = relationship(  # noqa: F821
        back_populates="agent",
        cascade="all, delete-orphan",
    )
