"""KnowledgeDocument model — tracks uploaded files per agent."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class KnowledgeDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf | docx | txt
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="processing", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata extracted during parsing
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
