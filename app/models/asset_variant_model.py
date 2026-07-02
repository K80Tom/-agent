"""资产变体 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetVariant(Base):
    """对应 common.asset_variants。"""

    __tablename__ = "asset_variants"
    __table_args__ = {"schema": "common"}

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    asset_entity_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("common.asset_entities.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    variant_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    usage_context: Mapped[str | None] = mapped_column(String(255))
    visual_prompt: Mapped[str | None] = mapped_column(Text)
    approved: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_file_url: Mapped[str | None] = mapped_column(String(1024))
    source_text: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))