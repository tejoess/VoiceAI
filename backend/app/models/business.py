"""Business / organization model.

A business owns agents and supplies the Business prompt layer (company name,
description, policies). In a single-tenant dev setup there is one default
business; the schema is multi-tenant ready.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Business(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-form business context injected into the Business prompt layer.
    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    agents: Mapped[list["Agent"]] = relationship(  # noqa: F821
        back_populates="business",
        cascade="all, delete-orphan",
    )
