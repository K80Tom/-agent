"""资产主体 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


SHANGHAI_NOW = text("(now() AT TIME ZONE 'Asia/Shanghai')")


class AssetEntity(Base):
    """对应 common.asset_entities。"""

    __tablename__ = "asset_entities"
    __table_args__ = (
        UniqueConstraint(
            "source_project_id",
            "asset_kind",
            "name",
            name="asset_entities_project_kind_name_uidx",
        ),
        {"schema": "common"},
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_project_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    source_project_name: Mapped[str | None] = mapped_column(String(128))
    asset_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    intro: Mapped[str | None] = mapped_column(Text)
    appearance: Mapped[str | None] = mapped_column(Text)
    age_value: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(16))
    height_cm: Mapped[int | None] = mapped_column(Integer)
    hair_description: Mapped[str | None] = mapped_column(String(512))
    outfit_description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    style_tags: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    approved: Mapped[bool | None] = mapped_column(Boolean)
    reuse_scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'all_projects'"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
    )
    source_file_url: Mapped[str | None] = mapped_column(String(1024))
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=SHANGHAI_NOW,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=SHANGHAI_NOW,
    )
    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
